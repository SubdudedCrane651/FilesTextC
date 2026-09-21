#include <curses.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#define MAX_ITEMS 2048
#define PATH_MAX_LEN 4096

typedef struct {
    char path[PATH_MAX_LEN];
    char *items[MAX_ITEMS];
    int count;
    int index;
    int scroll;
} Panel;

void free_items(Panel *p) {
    for (int i = 0; i < p->count; i++) {
        free(p->items[i]);
    }
    p->count = 0;
}

void list_dir(Panel *p) {
    DIR *d;
    struct dirent *ent;

    free_items(p);
    p->index = 0;
    p->scroll = 0;

    d = opendir(p->path);
    if (!d) {
        p->items[p->count++] = strdup("<permission denied>");
        return;
    }

    // add parent entry
    p->items[p->count++] = strdup("..");

    while ((ent = readdir(d)) != NULL && p->count < MAX_ITEMS) {
        p->items[p->count++] = strdup(ent->d_name);
    }
    closedir(d);
}

int is_dir(const char *dir, const char *name) {
    char full[PATH_MAX_LEN];
    struct stat st;
    snprintf(full, sizeof(full), "%s/%s", dir, name);
    if (stat(full, &st) == 0 && S_ISDIR(st.st_mode)) return 1;
    return 0;
}

int is_exec(const char *dir, const char *name) {
    char full[PATH_MAX_LEN];
    struct stat st;
    snprintf(full, sizeof(full), "%s/%s", dir, name);
    if (stat(full, &st) == 0 && (st.st_mode & S_IXUSR)) return 1;
    return 0;
}

void copy_item(const char *src_dir, const char *name, const char *dst_dir) {
    char src[PATH_MAX_LEN], dst[PATH_MAX_LEN];
    snprintf(src, sizeof(src), "%s/%s", src_dir, name);
    snprintf(dst, sizeof(dst), "%s/%s", dst_dir, name);

    // simple file copy (no dirs)
    FILE *fs = fopen(src, "rb");
    if (!fs) return;
    FILE *fd = fopen(dst, "wb");
    if (!fd) { fclose(fs); return; }

    char buf[8192];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), fs)) > 0) {
        fwrite(buf, 1, n, fd);
    }
    fclose(fs);
    fclose(fd);
}

void move_item(const char *src_dir, const char *name, const char *dst_dir) {
    char src[PATH_MAX_LEN], dst[PATH_MAX_LEN];
    snprintf(src, sizeof(src), "%s/%s", src_dir, name);
    snprintf(dst, sizeof(dst), "%s/%s", dst_dir, name);
    rename(src, dst);
}

void delete_item(const char *dir, const char *name) {
    char full[PATH_MAX_LEN];
    snprintf(full, sizeof(full), "%s/%s", dir, name);
    remove(full);
}

int confirm_dialog(const char *message) {
    int h, w;
    getmaxyx(stdscr, h, w);
    int win_h = 5;
    int win_w = (int)strlen(message) + 10;
    int win_y = (h - win_h) / 2;
    int win_x = (w - win_w) / 2;

    WINDOW *win = newwin(win_h, win_w, win_y, win_x);
    box(win, 0, 0);
    mvwprintw(win, 1, 2, "%s", message);
    mvwprintw(win, 3, 2, "[Y]es   [N]o");
    wrefresh(win);

    int ch;
    while (1) {
        ch = wgetch(win);
        if (ch == 'y' || ch == 'Y') {
            delwin(win);
            return 1;
        }
        if (ch == 'n' || ch == 'N') {
            delwin(win);
            return 0;
        }
    }
}

void draw_panel(Panel *p, int active, int startx, int width) {
    int h, w;
    getmaxyx(stdscr, h, w);
    int visible = h - 3;

    mvprintw(0, startx + 1, "%.*s", width - 2, p->path);

    int start = p->scroll;
    int end = p->scroll + visible;
    if (end > p->count) end = p->count;

    for (int i = start; i < end; i++) {
        int y = (i - start) + 1;
        char *name = p->items[i];
        char display[PATH_MAX_LEN];
        snprintf(display, sizeof(display), "%s%s",
                 name, is_dir(p->path, name) ? "/" : "");

        int attr = A_NORMAL;
        if (active && i == p->index) attr |= A_REVERSE;

        // color
        int color = 0;
        if (is_dir(p->path, name)) {
            color = COLOR_PAIR(1);
        } else if (is_exec(p->path, name)) {
            color = COLOR_PAIR(2);
        } else {
            color = COLOR_PAIR(3);
        }

        mvaddnstr(y, startx + 1, display, width - 2);
        mvchgat(y, startx + 1, width - 2, attr, 0, NULL);
        mvchgat(y, startx + 1, (int)strlen(display), attr | color, 0, NULL);
    }
}

void edit_file(const char *dir, const char *name) {
    char full[PATH_MAX_LEN];
    snprintf(full, sizeof(full), "%s/%s", dir, name);
#ifdef _WIN32
    char cmd[PATH_MAX_LEN + 32];
    snprintf(cmd, sizeof(cmd), "notepad \"%s\"", full);
    endwin();
    system(cmd);
    refresh();
#else
    char cmd[PATH_MAX_LEN + 32];
    snprintf(cmd, sizeof(cmd), "nano \"%s\"", full);
    endwin();
    system(cmd);
    refresh();
#endif
}

void command_line() {
    int h, w;
    getmaxyx(stdscr, h, w);
    move(h - 2, 1);
    clrtoeol();
    mvprintw(h - 2, 1, "Command: ");
    echo();
    char cmd[512];
    getnstr(cmd, sizeof(cmd) - 1);
    noecho();
    endwin();
    system(cmd);
    refresh();
}

int main(void) {
    Panel left, right;
    getcwd(left.path, sizeof(left.path));
    getcwd(right.path, sizeof(right.path));
    left.count = right.count = 0;
    left.index = right.index = 0;
    left.scroll = right.scroll = 0;

    initscr();
    noecho();
    cbreak();
    keypad(stdscr, TRUE);
    curs_set(0);

    start_color();
    use_default_colors();
    init_pair(1, COLOR_BLUE, -1);
    init_pair(2, COLOR_GREEN, -1);
    init_pair(3, -1, -1);

    list_dir(&left);
    list_dir(&right);

    int active_left = 1;

    while (1) {
        clear();
        int h, w;
        getmaxyx(stdscr, h, w);
        int half = w / 2;

        draw_panel(&left, active_left, 0, half);
        draw_panel(&right, !active_left, half, w - half);

        mvprintw(h - 1, 1,
                 "F2 Cmd  F4 Edit  F5 Copy  F6 Move  F8 Delete  Tab Switch  PgUp/PgDn Home/End  q Quit");
        refresh();

        int ch = getch();

        if (ch == 'q') break;

        else if (ch == '\t') {
            active_left = !active_left;
        }

        else if (ch == KEY_UP) {
            Panel *p = active_left ? &left : &right;
            if (p->index > 0) {
                p->index--;
                if (p->index < p->scroll) p->scroll--;
                if (p->scroll < 0) p->scroll = 0;
            }
        }

        else if (ch == KEY_DOWN) {
            Panel *p = active_left ? &left : &right;
            if (p->index < p->count - 1) {
                p->index++;
                int h2, w2;
                getmaxyx(stdscr, h2, w2);
                int visible = h2 - 3;
                if (p->index >= p->scroll + visible) p->scroll++;
            }
        }

        else if (ch == KEY_PPAGE) {
            int h2, w2;
            getmaxyx(stdscr, h2, w2);
            int visible = h2 - 3;
            Panel *p = active_left ? &left : &right;
            p->index -= visible;
            if (p->index < 0) p->index = 0;
            p->scroll -= visible;
            if (p->scroll < 0) p->scroll = 0;
        }

        else if (ch == KEY_NPAGE) {
            int h2, w2;
            getmaxyx(stdscr, h2, w2);
            int visible = h2 - 3;
            Panel *p = active_left ? &left : &right;
            p->index += visible;
            if (p->index > p->count - 1) p->index = p->count - 1;
            p->scroll += visible;
            if (p->scroll > p->count - visible)
                p->scroll = p->count - visible;
            if (p->scroll < 0) p->scroll = 0;
        }

        else if (ch == KEY_HOME) {
            Panel *p = active_left ? &left : &right;
            p->index = 0;
            p->scroll = 0;
        }

        else if (ch == KEY_END) {
            Panel *p = active_left ? &left : &right;
            p->index = p->count - 1;
            int h2, w2;
            getmaxyx(stdscr, h2, w2);
            int visible = h2 - 3;
            p->scroll = p->count - visible;
            if (p->scroll < 0) p->scroll = 0;
        }
else if (ch == KEY_ENTER || ch == '\n') {
    Panel *p = active_left ? &left : &right;
    char *name = p->items[p->index];

    // --- GO UP DIRECTORY ---
    if (strcmp(name, "..") == 0) {

        char *slash1 = strrchr(p->path, '/');
        char *slash2 = strrchr(p->path, '\\');
        char *slash = (slash1 > slash2 ? slash1 : slash2);

        if (slash && slash != p->path) {
            *slash = '\0';
        }

        list_dir(p);
        p->index = 0;
        p->scroll = 0;

        // DO NOT return from main()
    }

    // --- GO DOWN DIRECTORY ---
    else if (is_dir(p->path, name)) {

        char newpath[PATH_MAX_LEN];
        snprintf(newpath, sizeof(newpath), "%s/%s", p->path, name);

        snprintf(p->path, sizeof(p->path), "%s", newpath);

        list_dir(p);
        p->index = 0;
        p->scroll = 0;

        // DO NOT return from main()
    }
}


        

        else if (ch == KEY_F(2)) {
            command_line();
            list_dir(&left);
            list_dir(&right);
        }

        else if (ch == KEY_F(4)) {
            Panel *p = active_left ? &left : &right;
            char *name = p->items[p->index];
            if (strcmp(name, "..") != 0 && !is_dir(p->path, name)) {
                edit_file(p->path, name);
                list_dir(&left);
                list_dir(&right);
            }
        }

        else if (ch == KEY_F(5)) {
            Panel *src = active_left ? &left : &right;
            Panel *dst = active_left ? &right : &left;
            char *name = src->items[src->index];
            if (strcmp(name, "..") != 0) {
                char msg[PATH_MAX_LEN + 32];
                snprintf(msg, sizeof(msg), "Copy '%s'?", name);
                if (confirm_dialog(msg)) {
                    copy_item(src->path, name, dst->path);
                    list_dir(dst);
                }
            }
        }

        else if (ch == KEY_F(6)) {
            Panel *src = active_left ? &left : &right;
            Panel *dst = active_left ? &right : &left;
            char *name = src->items[src->index];
            if (strcmp(name, "..") != 0) {
                char msg[PATH_MAX_LEN + 32];
                snprintf(msg, sizeof(msg), "Move '%s'?", name);
                if (confirm_dialog(msg)) {
                    move_item(src->path, name, dst->path);
                    list_dir(src);
                    list_dir(dst);
                }
            }
        }

        else if (ch == KEY_F(8)) {
            Panel *p = active_left ? &left : &right;
            char *name = p->items[p->index];
            if (strcmp(name, "..") != 0) {
                char msg[PATH_MAX_LEN + 32];
                snprintf(msg, sizeof(msg), "Delete '%s'?", name);
                if (confirm_dialog(msg)) {
                    delete_item(p->path, name);
                    list_dir(p);
                }
            }
        }
    }

    endwin();
    free_items(&left);
    free_items(&right);
    return 0;
}
