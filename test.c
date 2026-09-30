#include <curses.h>
#include <windows.h>
#include <stdio.h>

int main() {
    printf("Starting test_curses...\n");
    Sleep(1000);  // 1 second so you can see this in PowerShell

    initscr();
    noecho();
    cbreak();
    keypad(stdscr, TRUE);
    start_color();
    use_default_colors();

    init_pair(1, COLOR_YELLOW, COLOR_BLUE);

    bkgd(COLOR_PAIR(1));
    clear();

    mvprintw(5, 10, "Curses is working!");
    mvprintw(7, 10, "Press any key to exit.");
    refresh();

    getch();

    endwin();
    return 0;
}
