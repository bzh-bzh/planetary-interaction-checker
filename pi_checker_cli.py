#!bin/python
from pg import DB
import Character
import click


@click.command()
@click.option('--name', '-n', help='Character\'s name.')
@click.option('--display', '-d', 'action', flag_value='display', default=True, help='Display the colonies. Default.')
@click.option('--export', '-e', 'action', flag_value='export', help='Export the DOT graph of the colonies.')
def main(name, action):
    # noinspection PyArgumentList
    planetary_interaction_db = DB(dbname='planetary_interaction_checker')

    character_name_query = planetary_interaction_db.query('select character_name, character_id from characters')
    character_name_dict = {}
    for pair in character_name_query.getresult():
        character_name_dict[pair[0]] = pair[1]

    if name is None:
        click.confirm('Are you sure you want to log in with a new character?', abort=True)
        character = Character.Character()
    else:
        if name in character_name_dict:
            character = Character.Character(character_name_dict[name])
        else:
            click.echo('This character name is not stored in the database. Existing names are: ')
            for name in character_name_dict.keys():
                click.echo(name)
            click.echo()
            raise click.Abort

    while True:
        click.echo()
        for i, colony in enumerate(character.colony_list):
            click.echo('[' + str(i) + ']\t' + colony.planet_name + '\t' + colony.planet_type.title())
        click.echo()
        try:
            if action is 'display':
                character.colony_list[click.prompt('Which planet would you like to display', type=int)].display()
            else:
                character.colony_list[click.prompt('Which planet would you like to display', type=int)].export_dot()
        except IndexError:
            click.echo('Choose a valid planet.')
        else:
            break


if __name__ == '__main__':
    main()
