#!/usr/bin/env python3
"""
    The MIT License (MIT)

    Copyright (c) 2023 pkjmesra

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

"""
import click
# # SOURCE: https://docs.python.org/2/library/curses.html
# # SOURCE: https://docs.python.org/3/howto/curses.html

# # For Windows: pip install windows-curses
# import curses
# window = curses.initscr() # Initialize the library. Returns a WindowObject which represents the whole screen.
# window.keypad(True) # Escape sequences generated by some keys (keypad, function keys) will be interpreted by curses.
# curses.cbreak() # Keys are read one by one. Also safer than curses.raw() because you can interrupt a running script with SIGINT (Ctrl + C).
# curses.noecho() # Prevent getch() keys from being visible when pressed. Echoing of input characters is turned off.

# # Initialize colors.
# curses.start_color() # Must be called if you want to use colors.
# curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
# curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLACK)
# curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
# curses.init_pair(4, curses.COLOR_GREEN, curses.COLOR_BLACK)
# curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK)
# curses.init_pair(6, curses.COLOR_BLUE, curses.COLOR_BLACK)
# curses.init_pair(7, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
# curses.init_pair(8, curses.COLOR_CYAN, curses.COLOR_BLACK)
# black = curses.color_pair(1)
# white = curses.color_pair(2)
# red = curses.color_pair(3)
# green = curses.color_pair(4)
# yellow = curses.color_pair(5)
# blue = curses.color_pair(6)
# magenta = curses.color_pair(7)
# cyan = curses.color_pair(8)

# # -----

# def draw_menu(menuItems, selectedIndex):
#     #  window.erase()
#     window.clear()

#     # Print a vertical menu.
#     line = 1
#     for i in range(len(menuItems)):
#         window.addstr(' ')
#         newLines = ""
#         menu = menuItems[i]
#         menuText = menu.keyTextLabel()
#         if line != menu.line:
#           window.addstr('\n')
#           line += 1
#         window.addstr(f"{menuText}\n", black if i == selectedIndex else white)
#         #   line += 1
#         line += 1

#     # # Print a dividing line.
#     # window.addstr(('-' * 80) + '\n')

#     # # Print a horizontal menu.
#     # for i in range(len(menuItems)):
#     #     window.addstr(' ')
#     #     window.addstr(menuItems[i], black if i == selectedIndex else white)

#     # window.addstr('\n')

# # -----

# def process_input(menuItems, selectedIndex):
#     userInput = window.getch()

#     if userInput == curses.KEY_LEFT or userInput == curses.KEY_UP:
#         # Loop around backwards.
#         selectedIndex = (selectedIndex - 1 + len(menuItems)) % len(menuItems)

#     elif userInput == curses.KEY_RIGHT or userInput == curses.KEY_DOWN:
#         # Loop around forwards.
#         selectedIndex = (selectedIndex + 1) % len(menuItems)

#     # If curses.nonl() is called, Enter key = \r else \n.
#     elif userInput == curses.KEY_ENTER or chr(userInput) in '\r\n':
#         # If the last option, exit, is selected.
#         if selectedIndex == len(menuItems) - 1:
#             wait_for_any_keypress()
#             curses.endwin() # De-initialize the library, and return terminal to normal status.    <-- Works without this on Windows, however in Linux you can't type in the terminal after exiting without this :P
#             exit(0)

#         window.addstr('\n Selected index: {}\n'.format(selectedIndex))
#         # wait_for_any_keypress()

#     else:
#         window.addstr("\n The pressed key '{}' {} is not associated with a menu function.\n".format(chr(userInput), userInput))
#         # wait_for_any_keypress()

#     return selectedIndex

# # -----

# def wait_for_any_keypress():
#     window.addstr('\n Press any key to continue . . . ')
#     window.getch()

# # -----

# def main():
#     selectedIndex = 0
#     while True:
#         draw_menu(MENU_ITEMS, selectedIndex)
#         selectedIndex = process_input(MENU_ITEMS, selectedIndex)

# from pkscreener.classes.MenuOptions import menus
# m = menus()

# MENU_ITEMS = m.renderForMenu(asList=True)
# #[
# #     ' Option 1 ',
# #     ' Option 2 ',
# #     ' Option 3 ',
# #     ' Exit ',
# # ]

# if __name__ == '__main__':
#     main()

def getKeyBoardArrowInput(message="Use Left / Right arrow keys to slide (going back / forward) the time-window!"):
    printable = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
    direction = None
    click.echo(message, nl=True)
    c = click.getchar()
    click.echo()
    supportedDirections = {'\x1b[A':'UP','\x1b[B':'DOWN','\x1b[C':'RIGHT','\x1b[D':'LEFT'}
    if not c in supportedDirections.keys():
        click.echo('Invalid input :(')
        click.echo('You pressed: "' + ''.join([ '\\'+hex(ord(i))[1:] if i not in printable else i for i in c ]) +'"' )
    else:
        direction = supportedDirections.get(c)
    return direction
