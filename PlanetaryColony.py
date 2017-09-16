import webbrowser
import datetime
from pg import DB
from collections import defaultdict
import pygraphviz
import matplotlib.pyplot as plot
import matplotlib.colors
import uuid


class PlanetaryColony:
    # noinspection PyArgumentList
    eve_info_db = DB(dbname='eve_info')

    def __init__(self, colony_json):
        assert type(colony_json) is dict

        # TODO: Find out if this is in EVE time or in UTC.
        self.last_update = datetime.datetime.strptime(colony_json['last_update'], '%Y-%m-%dT%XZ')
        self.planet_type = colony_json['planet_type']
        self.planet_name = colony_json['name']
        self.solar_system_id = colony_json['solar_system_id']
        self.command_center_upgrade_level = colony_json['upgrade_level']

        colony_layout_dict = colony_json['colony_layout']

        """
         we insert the nodes first, then create two graphs--one undirected for the physical layer, and a digraph for
         the route layer.
        """
        colony_base_nodes = pygraphviz.AGraph(strict=False)

        # insert the nodes
        for pin in colony_layout_dict['pins']:
            pin_id = pin['pin_id']
            type_name = self.eve_info_db.query('select "typeName" from "invTypes" where "typeID"='
                                               + str(pin['type_id'])).dictresult()[0]['typeName'].replace(' ', '\n')

            colony_base_nodes.add_node(pin_id, type_id=pin['type_id'], label=type_name,
                                       pos=str(pin['latitude'] * 300) + ',' + str(pin['longitude'] * 300) + '!',
                                       shape='rectangle',
                                       style='filled', color='white',
                                       fontname='monospace')

            current_node = colony_base_nodes.get_node(pin_id)

            if 'schematic_id' in pin:
                schematic_name = self.eve_info_db.query('select "schematicName" from "planetSchematics"'
                                                        ' where "schematicID"='
                                                        + str(pin['schematic_id'])).dictresult()[0]['schematicName']

                current_node.attr['schematic_id'] = pin['schematic_id']
                current_node.attr['schematic_name'] = schematic_name
                if 'Advanced' in type_name:
                    current_node.attr['shape'] = 'doubleoctagon'
                else:
                    current_node.attr['shape'] = 'octagon'

            if 'extractor_details' in pin:
                extractor_product_type_id = pin['extractor_details']['product_type_id']
                extractor_product_name = self.eve_info_db.query('select "typeName" from "invTypes" where "typeID"='
                                                        + str(extractor_product_type_id)).dictresult()[0]['typeName']
                extractor_qty_per_cycle = pin['extractor_details']['qty_per_cycle']
                current_node.attr['extractor_product_type_id'] = extractor_product_type_id
                current_node.attr['extractor_product_name'] = extractor_product_name
                current_node.attr['extractor_qty_per_cycle'] = extractor_qty_per_cycle
                current_node.attr['shape'] = 'trapezium'

        # insert the links
        self.colony_link_graph = colony_base_nodes.copy()

        for link in colony_layout_dict['links']:
            self.colony_link_graph.add_edge(link['source_pin_id'], link['destination_pin_id'],
                                            link_level=link['link_level'], penwidth=2, color='white')

        # insert the routes
        self.colony_route_graph = colony_base_nodes.copy().to_directed()

        color_key_dict = {}
        color_map = plot.get_cmap('Vega20')

        for route in colony_layout_dict['routes']:
            content_type_id = route['content_type_id']

            content_type_name = self.eve_info_db.query('select "typeName" from "invTypes" where "typeID"='
                                                       + str(content_type_id)).dictresult()[0]['typeName']

            content_uid = self.eve_info_db.query('select uid from "planetaryInteractionItems" where "typeID"='
                                                 + str(content_type_id)).dictresult()[0]['uid']

            # 1 is the minimum PI unique ID, and 83 the max.
            normalized_type_id = ((content_uid - 1) / (83 - 1))
            content_color = matplotlib.colors.rgb2hex(color_map(normalized_type_id)[:3])

            color_key_dict[content_type_name] = content_color

            # TODO: Add a color key.
            self.colony_route_graph.add_edge(route['source_pin_id'], route['destination_pin_id'],
                                             content_type_id=content_type_id,
                                             color=content_color, penwidth=2, fontname='monospace')

        """
         add invisible edges so the nodes line up and compact properly
        """
        node_schematic_dict_list = []
        for i in self.colony_route_graph.nodes():
            node_attr = self.colony_route_graph.get_node(i).attr
            if 'schematic_id' in node_attr.keys() and 'High-Tech' not in node_attr['label']:
                node_schematic_dict_list.append({i.get_name(): node_attr['schematic_id']})

        # group the nodes by their schematic IDs
        grouped_node_dict = defaultdict(list)
        for d in node_schematic_dict_list:
            for key, value in sorted(d.items()):
                grouped_node_dict[value].append(key)

        # stick the groups in a subgraph, and connect them with invisible edges so they stay together
        for key, value in grouped_node_dict.items():
            self.colony_route_graph.add_subgraph(value, rank='same')
            for node, next_node in self.window(iter(value)):
                self.colony_route_graph.add_edge(node, next_node, style='invis', weight=9999, len=0)

        # connect nodes between the subgraphs
        for subgraph, next_subgraph in self.window(self.colony_route_graph.subgraphs_iter()):
            for subgraph_node, next_node in zip(subgraph.nodes(), next_subgraph.nodes()):
                self.colony_route_graph.add_edge(subgraph_node, next_node, style='invis', weight=9999, len=0)

        """
         create a legend for the graph
        """
        # product name --> arrow colored
        self.colony_legend_graph = pygraphviz.AGraph()
        for product, color in color_key_dict.items():
            product_node_uuid = int(uuid.uuid4())
            self.colony_legend_graph.add_node(product_node_uuid, label=product,
                                             fontcolor=color, shape='plaintext', fontname='monospace')

    def display(self):
        background_color = 'bgcolor=#404040'
        link_graph_filename = self.planet_name.replace(' ', '_') + '_link_graph.svg'
        route_graph_filename = self.planet_name.replace(' ', '_') + '_route_graph.svg'

        self.colony_link_graph.draw(link_graph_filename, prog='dot', args='-G'+background_color)
        self.colony_route_graph.draw(route_graph_filename, prog='dot', args='-G'+background_color)

        webbrowser.open_new_tab(link_graph_filename)
        webbrowser.open_new_tab(route_graph_filename)

    def export_dot(self):
        link_graph_filename = self.planet_name.replace(' ', '_') + '_link_graph.dot'
        route_graph_filename = self.planet_name.replace(' ', '_') + '_route_graph.dot'

        self.colony_link_graph.write(link_graph_filename)
        self.colony_route_graph.write(route_graph_filename)

    # sliding window iterator. for a list of [a b c] it goes [a b] then [b c].
    @staticmethod
    def window(iterable, size=2):
        i = iter(iterable)
        win = []
        for e in range(0, size):
            win.append(next(i))
        yield win
        for e in i:
            win = win[1:] + [e]
            yield win
