from pathlib import Path

root = Path("/mnt/data/TextFileManager_CrossPlatform")
src = root / "src"
vscode = root / ".vscode"
src.mkdir(parents=True, exist_ok=True)
vscode.mkdir(parents=True, exist_ok=True)

main_c = r'''/*
 * TextFileManager - Midnight Commander style text/file manager
 * C11 - Windows, Linux and macOS
 *
 * Windows: native Win32 console API; no PDCurses required.
 * Linux/macOS: ncurses.
 */

#ifdef _WIN32
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <conio.h>
#include <direct.h>
#define PATH_SEP '\\'
#define PATH_SEP_STR "\\"
#define getcwd _getcwd
#define chdir _chdir
#else
#include <ncurses.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <limits.h>
#include <strings.h>
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <time.h>
#include <errno.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#define MAX_ITEMS 4096
#define MAX_NAME 512
#define EDIT_LINES 8192
#define EDIT_COLS 4096

enum {
    KEY_UP2 = 1001, KEY_DOWN2, KEY_LEFT2, KEY_RIGHT2,
    KEY_PGUP2, KEY_PGDN2, KEY_HOME2, KEY_END2,
    KEY_F_BASE = 1100, KEY_MOUSE2 = 1200
};

typedef struct {
    char name[MAX_NAME];
    int is_dir;
    long long size;
    time_t mtime;
} FileItem;

typedef struct {
    char path[PATH_MAX];
    FileItem items[MAX_ITEMS];
    int count;
    int selected;
    int top;
} Panel;

static Panel panels[2];
static int active_panel = 0;
static int running = 1;
static int screen_w = 120, screen_h = 30;
static char status_msg[512] = "F3 View  F4 Edit  F5 Copy  F6 Move  F7 Mkdir  F8 Delete  F10 Quit";

#ifdef _WIN32
static HANDLE hout, hin;
static DWORD old_in_mode;
static WORD default_attr = FOREGROUND_RED | FOREGROUND_GREEN | FOREGROUND_BLUE;
#endif

static void set_status(const char *s)
{
    snprintf(status_msg, sizeof(status_msg), "%s", s ? s : "");
}

static void join_path(char *out, size_t n, const char *a, const char *b)
{
    size_t la = strlen(a);
    if (la && (a[la - 1] == '/' || a[la - 1] == '\\'))
        snprintf(out, n, "%s%s", a, b);
    else
        snprintf(out, n, "%s%c%s", a, PATH_SEP, b);
}

static int is_dot_name(const char *n)
{
    return strcmp(n, ".") == 0 || strcmp(n, "..") == 0;
}

#ifndef _WIN32
static int name_contains_ci(const char *name, const char *query)
{
    if (!query || !*query) return 1;
    size_t qlen = strlen(query);
    for (const char *p = name; *p; ++p) {
        size_t i = 0;
        while (i < qlen && p[i] &&
               tolower((unsigned char)p[i]) == tolower((unsigned char)query[i]))
            ++i;
        if (i == qlen) return 1;
    }
    return 0;
}
#else
static int name_contains_ci(const char *name, const char *query)
{
    if (!query || !*query) return 1;
    return StrStrIA(name, query) != NULL;
}
#endif

static int cmp_items(const void *pa, const void *pb)
{
    const FileItem *a = pa;
    const FileItem *b = pb;
    if (a->is_dir != b->is_dir) return b->is_dir - a->is_dir;
#ifdef _WIN32
    return _stricmp(a->name, b->name);
#else
    return strcasecmp(a->name, b->name);
#endif
}

static void load_panel(Panel *p)
{
    char old_name[MAX_NAME] = "";
    if (p->count > 0 && p->selected >= 0 && p->selected < p->count)
        snprintf(old_name, sizeof(old_name), "%s", p->items[p->selected].name);

    p->count = 0;

#ifdef _WIN32
    char pattern[PATH_MAX];
    snprintf(pattern, sizeof(pattern), "%s%c*", p->path, PATH_SEP);

    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA(pattern, &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (is_dot_name(fd.cFileName)) continue;
            if (p->count >= MAX_ITEMS) break;

            FileItem *it = &p->items[p->count++];
            snprintf(it->name, sizeof(it->name), "%s", fd.cFileName);
            it->is_dir = (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;

            ULARGE_INTEGER sz;
            sz.LowPart = fd.nFileSizeLow;
            sz.HighPart = fd.nFileSizeHigh;
            it->size = (long long)sz.QuadPart;

            FILETIME lft;
            SYSTEMTIME st;
            FileTimeToLocalFileTime(&fd.ftLastWriteTime, &lft);
            FileTimeToSystemTime(&lft, &st);

            struct tm tmv = {0};
            tmv.tm_year = st.wYear - 1900;
            tmv.tm_mon  = st.wMonth - 1;
            tmv.tm_mday = st.wDay;
            tmv.tm_hour = st.wHour;
            tmv.tm_min  = st.wMinute;
            tmv.tm_sec  = st.wSecond;
            it->mtime = mktime(&tmv);
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
#else
    DIR *d = opendir(p->path);
    if (d) {
        struct dirent *de;
        while ((de = readdir(d)) != NULL && p->count < MAX_ITEMS) {
            if (is_dot_name(de->d_name)) continue;

            FileItem *it = &p->items[p->count++];
            snprintf(it->name, sizeof(it->name), "%s", de->d_name);

            char full[PATH_MAX];
            join_path(full, sizeof(full), p->path, de->d_name);

            struct stat st;
            if (stat(full, &st) == 0) {
                it->is_dir = S_ISDIR(st.st_mode);
                it->size = (long long)st.st_size;
                it->mtime = st.st_mtime;
            }
        }
        closedir(d);
    }
#endif

    qsort(p->items, (size_t)p->count, sizeof(FileItem), cmp_items);
    p->selected = 0;

    if (old_name[0]) {
        for (int i = 0; i < p->count; ++i) {
#ifdef _WIN32
            if (_stricmp(old_name, p->items[i].name) == 0) {
#else
            if (strcasecmp(old_name, p->items[i].name) == 0) {
#endif
                p->selected = i;
                break;
            }
        }
    }

    if (p->count == 0) p->selected = 0;
    else if (p->selected >= p->count) p->selected = p->count - 1;
    p->top = 0;
}

static void init_panels(void)
{
    char cwd[PATH_MAX];
    if (!getcwd(cwd, sizeof(cwd)))
        snprintf(cwd, sizeof(cwd), ".");

    snprintf(panels[0].path, sizeof(panels[0].path), "%s", cwd);
    snprintf(panels[1].path, sizeof(panels[1].path), "%s", cwd);
    load_panel(&panels[0]);
    load_panel(&panels[1]);
}

static void format_size(long long n, char *out, size_t sz)
{
    if (n < 1024) snprintf(out, sz, "%lld", n);
    else if (n < 1024LL * 1024) snprintf(out, sz, "%.1fK", n / 1024.0);
    else if (n < 1024LL * 1024 * 1024) snprintf(out, sz, "%.1fM", n / (1024.0 * 1024.0));
    else snprintf(out, sz, "%.1fG", n / (1024.0 * 1024.0 * 1024.0));
}

static void format_time(time_t t, char *out, size_t sz)
{
    struct tm *tmv = localtime(&t);
    if (!tmv) {
        snprintf(out, sz, "----");
        return;
    }
    strftime(out, sz, "%Y-%m-%d %H:%M", tmv);
}

#ifdef _WIN32

static void win_goto(short x, short y)
{
    COORD c = { x, y };
    SetConsoleCursorPosition(hout, c);
}

static void win_color(WORD attr)
{
    SetConsoleTextAttribute(hout, attr);
}

static void clear_screen(void)
{
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    if (!GetConsoleScreenBufferInfo(hout, &csbi)) return;

    DWORD cells = (DWORD)csbi.dwSize.X * (DWORD)csbi.dwSize.Y;
    COORD home = {0, 0};
    DWORD written;
    FillConsoleOutputCharacterA(hout, ' ', cells, home, &written);
    FillConsoleOutputAttribute(hout, default_attr, cells, home, &written);
    win_goto(0, 0);
}

static void get_screen_size(void)
{
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    if (GetConsoleScreenBufferInfo(hout, &csbi)) {
        screen_w = csbi.srWindow.Right - csbi.srWindow.Left + 1;
        screen_h = csbi.srWindow.Bottom - csbi.srWindow.Top + 1;
    }
}

static void draw_text(int x, int y, int width, const char *s, WORD attr)
{
    if (y < 0 || y >= screen_h || width <= 0) return;

    char buf[2048];
    if (width >= (int)sizeof(buf)) width = (int)sizeof(buf) - 1;
    snprintf(buf, sizeof(buf), "%-*.*s", width, width, s ? s : "");

    win_goto((short)x, (short)y);
    win_color(attr);

    DWORD written;
    WriteConsoleA(hout, buf, (DWORD)width, &written, NULL);
}

static void ui_init(void)
{
    hout = GetStdHandle(STD_OUTPUT_HANDLE);
    hin = GetStdHandle(STD_INPUT_HANDLE);

    GetConsoleMode(hin, &old_in_mode);
    DWORD mode = old_in_mode;
    mode &= ~(ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT | ENABLE_PROCESSED_INPUT);
    mode |= ENABLE_EXTENDED_FLAGS | ENABLE_MOUSE_INPUT;
    SetConsoleMode(hin, mode);

    get_screen_size();
}

static void ui_shutdown(void)
{
    SetConsoleMode(hin, old_in_mode);
    win_color(default_attr);
    clear_screen();
}

static int read_key(void)
{
    INPUT_RECORD rec;
    DWORD got;

    while (ReadConsoleInputA(hin, &rec, 1, &got)) {
        if (rec.EventType == KEY_EVENT && rec.Event.KeyEvent.bKeyDown) {
            KEY_EVENT_RECORD *k = &rec.Event.KeyEvent;
            WORD vk = k->wVirtualKeyCode;

            if (vk == VK_UP) return KEY_UP2;
            if (vk == VK_DOWN) return KEY_DOWN2;
            if (vk == VK_LEFT) return KEY_LEFT2;
            if (vk == VK_RIGHT) return KEY_RIGHT2;
            if (vk == VK_PRIOR) return KEY_PGUP2;
            if (vk == VK_NEXT) return KEY_PGDN2;
            if (vk == VK_HOME) return KEY_HOME2;
            if (vk == VK_END) return KEY_END2;
            if (vk == VK_TAB) return '\t';
            if (vk == VK_BACK) return '\b';
            if (vk == VK_RETURN) return '\r';
            if (vk == VK_ESCAPE) return 27;
            if (vk >= VK_F1 && vk <= VK_F12)
                return KEY_F_BASE + (vk - VK_F1 + 1);
            if (k->uChar.AsciiChar)
                return (unsigned char)k->uChar.AsciiChar;
        }

        if (rec.EventType == MOUSE_EVENT &&
            (rec.Event.MouseEvent.dwButtonState & FROM_LEFT_1ST_BUTTON_PRESSED)) {
            /* Mouse is intentionally ignored for Windows in this portable build. */
        }
    }
    return 0;
}

#else

static void clear_screen(void) { erase(); }

static void get_screen_size(void)
{
    getmaxyx(stdscr, screen_h, screen_w);
}

static void draw_text(int x, int y, int width, const char *s, int attr)
{
    if (y < 0 || y >= screen_h || width <= 0) return;
    mvaddnstr(y, x, s ? s : "", width);
    (void)attr;
}

static void ui_init(void)
{
    initscr();
    cbreak();
    noecho();
    keypad(stdscr, TRUE);
    curs_set(0);
    get_screen_size();
}

static void ui_shutdown(void)
{
    endwin();
}

static int read_key(void)
{
    int c = getch();

    if (c == KEY_UP) return KEY_UP2;
    if (c == KEY_DOWN) return KEY_DOWN2;
    if (c == KEY_LEFT) return KEY_LEFT2;
    if (c == KEY_RIGHT) return KEY_RIGHT2;
    if (c == KEY_PPAGE) return KEY_PGUP2;
    if (c == KEY_NPAGE) return KEY_PGDN2;
    if (c == KEY_HOME) return KEY_HOME2;
    if (c == KEY_END) return KEY_END2;
    if (c >= KEY_F(1) && c <= KEY_F(12))
        return KEY_F_BASE + (c - KEY_F(1) + 1);

    return c;
}

#endif

static void draw_panel(const Panel *p, int which, int x, int y, int w, int h)
{
    int active = (which == active_panel);
    char title[PATH_MAX + 8];

    snprintf(title, sizeof(title), " %s ", p->path);
    draw_text(x, y, w, title,
#ifdef _WIN32
              active ? (BACKGROUND_BLUE | BACKGROUND_GREEN | BACKGROUND_RED) : default_attr
#else
              0
#endif
    );

    int list_y = y + 1;
    int list_h = h - 3;
    if (list_h < 1) return;

    int top = p->top;
    if (p->selected < top) top = p->selected;
    if (p->selected >= top + list_h) top = p->selected - list_h + 1;
    if (top < 0) top = 0;

    for (int row = 0; row < list_h; ++row) {
        int idx = top + row;
        char line[2048] = "";

        if (idx < p->count) {
            const FileItem *it = &p->items[idx];
            char sizebuf[32], timebuf[32];

            format_size(it->size, sizebuf, sizeof(sizebuf));
            format_time(it->mtime, timebuf, sizeof(timebuf));

            if (it->is_dir)
                snprintf(line, sizeof(line), "[%.*s]", w > 2 ? w - 2 : 1, it->name);
            else
                snprintf(line, sizeof(line), "%-*s %8s %s",
                         w > 28 ? w - 28 : 1, it->name, sizebuf, timebuf);
        }

        int selected = (idx == p->selected);

#ifdef _WIN32
        WORD attr = selected && active
            ? (BACKGROUND_BLUE | BACKGROUND_GREEN | BACKGROUND_RED)
            : default_attr;
        draw_text(x, list_y + row, w, line, attr);
#else
        if (selected && active) attron(A_REVERSE);
        draw_text(x, list_y + row, w, line, 0);
        if (selected && active) attroff(A_REVERSE);
#endif
    }

    char footer[64];
    snprintf(footer, sizeof(footer), "%d files", p->count);
    draw_text(x, y + h - 2, w, footer, 0);
}

static void draw_ui(void)
{
    get_screen_size();
    clear_screen();

    if (screen_w < 40 || screen_h < 12) {
#ifdef _WIN32
        draw_text(0, 0, screen_w, "Terminal too small. Resize it.", default_attr);
#else
        mvprintw(0, 0, "Terminal too small. Resize it.");
        refresh();
#endif
        return;
    }

    int panel_w = screen_w / 2;
    int panel_h = screen_h - 5;

    draw_panel(&panels[0], 0, 0, 0, panel_w, panel_h);
    draw_panel(&panels[1], 1, panel_w, 0, screen_w - panel_w, panel_h);

    draw_text(0, screen_h - 4, screen_w,
              "F3 View  F4 Edit  F5 Copy  F6 Move  F7 Mkdir  F8 Delete  F9 Search  F10 Quit", 0);
    draw_text(0, screen_h - 3, screen_w,
              "Tab Switch  Enter Open  Backspace Parent  N New File  R Rename", 0);
    draw_text(0, screen_h - 2, screen_w, status_msg, 0);

#ifdef _WIN32
    win_color(default_attr);
    win_goto(0, (short)(screen_h - 1));
#else
    refresh();
#endif
}

static int ask_line(const char *prompt, char *out, size_t n)
{
    if (n == 0) return 0;

#ifdef _WIN32
    DWORD mode;
    GetConsoleMode(hin, &mode);
    SetConsoleMode(hin, (mode & ~ENABLE_MOUSE_INPUT) |
                        ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT);

    win_goto(0, (short)(screen_h - 1));
    printf("%-*s", screen_w, "");
    win_goto(0, (short)(screen_h - 1));
    printf("%s", prompt);
    fflush(stdout);

    int ok = fgets(out, (int)n, stdin) != NULL;
    SetConsoleMode(hin, mode);
    if (!ok) return 0;
#else
    echo();
    curs_set(1);
    mvprintw(screen_h - 1, 0, "%-*s", screen_w, "");
    mvprintw(screen_h - 1, 0, "%s", prompt);
    getnstr(out, (int)n - 1);
    noecho();
    curs_set(0);
#endif

    out[strcspn(out, "\r\n")] = '\0';
    return 1;
}

static int confirm(const char *message)
{
    char answer[16] = "";
    if (!ask_line(message, answer, sizeof(answer))) return 0;
    return answer[0] == 'y' || answer[0] == 'Y';
}

static void parent_dir(Panel *p)
{
#ifdef _WIN32
    size_t len = strlen(p->path);
    while (len > 3 && (p->path[len - 1] == '\\' || p->path[len - 1] == '/'))
        p->path[--len] = '\0';

    char *last1 = strrchr(p->path, '\\');
    char *last2 = strrchr(p->path, '/');
    char *last = last1 > last2 ? last1 : last2;

    if (!last) return;
    if (last == p->path + 2 && p->path[1] == ':') {
        p->path[3] = '\0';
    } else if (last == p->path + 2 && p->path[1] == ':') {
        p->path[3] = '\0';
    } else if (last == p->path && p->path[1] == '\0') {
        return;
    } else {
        *last = '\0';
    }
#else
    char *last = strrchr(p->path, '/');
    if (!last) return;

    if (last == p->path) {
        p->path[1] = '\0';
    } else {
        *last = '\0';
    }
#endif

    load_panel(p);
}

static int make_dir_portable(const char *path)
{
#ifdef _WIN32
    return _mkdir(path);
#else
    return mkdir(path, 0755);
#endif
}

static int copy_file(const char *src, const char *dst)
{
    FILE *in = fopen(src, "rb");
    if (!in) return 0;

    FILE *out = fopen(dst, "wb");
    if (!out) {
        fclose(in);
        return 0;
    }

    char buf[64 * 1024];
    size_t n;
    int ok = 1;

    while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
        if (fwrite(buf, 1, n, out) != n) {
            ok = 0;
            break;
        }
    }

    if (ferror(in)) ok = 0;

    fclose(in);
    fclose(out);
    return ok;
}

static int delete_path(const char *path, int is_dir)
{
#ifdef _WIN32
    return is_dir ? RemoveDirectoryA(path) : DeleteFileA(path);
#else
    return is_dir ? rmdir(path) : remove(path);
#endif
}

static void action_mkdir(void)
{
    char name[MAX_NAME];
    if (!ask_line("New directory: ", name, sizeof(name)) || !name[0]) return;

    char path[PATH_MAX];
    join_path(path, sizeof(path), panels[active_panel].path, name);

    if (make_dir_portable(path) == 0) {
        load_panel(&panels[active_panel]);
        set_status("Directory created.");
    } else {
        set_status("Could not create directory.");
    }
}

static void action_new_file(void)
{
    char name[MAX_NAME];
    if (!ask_line("New text file: ", name, sizeof(name)) || !name[0]) return;

    char path[PATH_MAX];
    join_path(path, sizeof(path), panels[active_panel].path, name);

    FILE *f = fopen(path, "wb");
    if (!f) {
        set_status("Could not create file.");
        return;
    }

    fclose(f);
    load_panel(&panels[active_panel]);
    set_status("File created.");
}

static void action_rename(void)
{
    Panel *p = &panels[active_panel];
    if (p->count == 0) return;

    char oldp[PATH_MAX], newp[PATH_MAX], name[MAX_NAME];
    join_path(oldp, sizeof(oldp), p->path, p->items[p->selected].name);

    if (!ask_line("New name: ", name, sizeof(name)) || !name[0]) return;

    join_path(newp, sizeof(newp), p->path, name);

    if (rename(oldp, newp) == 0) {
        load_panel(p);
        set_status("Renamed.");
    } else {
        set_status("Rename failed.");
    }
}

static void action_delete(void)
{
    Panel *p = &panels[active_panel];
    if (p->count == 0) return;

    FileItem *it = &p->items[p->selected];
    char msg[700];

    snprintf(msg, sizeof(msg), "Delete '%s'? Type y: ", it->name);
    if (!confirm(msg)) return;

    char path[PATH_MAX];
    join_path(path, sizeof(path), p->path, it->name);

    if (delete_path(path, it->is_dir) == 0) {
        load_panel(p);
        set_status("Deleted.");
    } else {
        set_status(it->is_dir ? "Directory must be empty." : "Delete failed.");
    }
}

static void action_copy_move(int move)
{
    Panel *srcp = &panels[active_panel];
    Panel *dstp = &panels[1 - active_panel];

    if (srcp->count == 0) return;

    FileItem *it = &srcp->items[srcp->selected];
    if (it->is_dir) {
        set_status("Directory copy/move is not implemented.");
        return;
    }

    char src[PATH_MAX], dst[PATH_MAX];
    join_path(src, sizeof(src), srcp->path, it->name);
    join_path(dst, sizeof(dst), dstp->path, it->name);

    if (!copy_file(src, dst)) {
        set_status("Copy failed.");
        return;
    }

    if (move) {
        if (remove(src) != 0)
            set_status("Copied, but could not remove original.");
        else
            set_status("Moved.");
    } else {
        set_status("Copied.");
    }

    load_panel(srcp);
    load_panel(dstp);
}

static void show_file(const char *path, int edit);

static void action_open(void)
{
    Panel *p = &panels[active_panel];
    if (p->count == 0) return;

    FileItem *it = &p->items[p->selected];
    char path[PATH_MAX];
    join_path(path, sizeof(path), p->path, it->name);

    if (it->is_dir) {
        snprintf(p->path, sizeof(p->path), "%s", path);
        load_panel(p);
    } else {
        show_file(path, 1);
        load_panel(p);
    }
}

static void action_view(void)
{
    Panel *p = &panels[active_panel];
    if (p->count == 0 || p->items[p->selected].is_dir) return;

    char path[PATH_MAX];
    join_path(path, sizeof(path), p->path, p->items[p->selected].name);
    show_file(path, 0);
}

static void action_search(void)
{
    char query[MAX_NAME];

    if (!ask_line("Find name: ", query, sizeof(query)) || !query[0]) return;

    Panel *p = &panels[active_panel];
    for (int i = 0; i < p->count; ++i) {
        if (name_contains_ci(p->items[i].name, query)) {
            p->selected = i;
            set_status("Match found.");
            return;
        }
    }

    set_status("No match in current directory.");
}

static int save_editor(char **lines, int count, const char *path)
{
    FILE *out = fopen(path, "wb");
    if (!out) return 0;

    for (int i = 0; i < count; ++i) {
        fputs(lines[i], out);
        if (i + 1 < count) fputc('\n', out);
    }

    int ok = !ferror(out);
    fclose(out);
    return ok;
}

static void show_file(const char *path, int edit)
{
    FILE *f = fopen(path, "rb");
    if (!f) {
        set_status("Cannot open file.");
        return;
    }

    char **lines = calloc(EDIT_LINES, sizeof(char *));
    if (!lines) {
        fclose(f);
        set_status("Not enough memory.");
        return;
    }

    int count = 0;
    char buffer[EDIT_COLS];

    while (count < EDIT_LINES && fgets(buffer, sizeof(buffer), f)) {
        size_t len = strlen(buffer);
        while (len && (buffer[len - 1] == '\n' || buffer[len - 1] == '\r'))
            buffer[--len] = '\0';

        lines[count] = malloc(len + 1);
        if (!lines[count]) break;

        memcpy(lines[count], buffer, len + 1);
        ++count;
    }
    fclose(f);

    if (count == 0) {
        lines[0] = malloc(1);
        if (!lines[0]) {
            free(lines);
            return;
        }
        lines[0][0] = '\0';
        count = 1;
    }

    int row = 0, col = 0, top = 0, dirty = 0, done = 0;

    while (!done) {
        get_screen_size();
        clear_screen();

#ifdef _WIN32
        draw_text(0, 0, screen_w,
                  edit ? "EDITOR  F2 Save  F10 Exit" : "VIEWER  F10 Exit",
                  default_attr);
#else
        mvprintw(0, 0, "%s", edit ? "EDITOR  F2 Save  F10 Exit" : "VIEWER  F10 Exit");
#endif

        int visible = screen_h - 3;
        if (visible < 1) visible = 1;

        if (row < top) top = row;
        if (row >= top + visible) top = row - visible + 1;

        for (int i = 0; i < visible; ++i) {
            int idx = top + i;
            if (idx >= count) break;
#ifdef _WIN32
            draw_text(0, i + 1, screen_w, lines[idx], default_attr);
#else
            mvaddnstr(i + 1, 0, lines[idx], screen_w);
#endif
        }

        char info[256];
        snprintf(info, sizeof(info), "%s  line %d/%d  col %d",
                 dirty ? "[modified]" : "", row + 1, count, col + 1);
        draw_text(0, screen_h - 2, screen_w, info, 0);

#ifdef _WIN32
        int cx = col < screen_w ? col : screen_w - 1;
        int cy = 1 + row - top;
        if (cy < 1) cy = 1;
        if (cy >= screen_h - 2) cy = screen_h - 3;
        win_goto((short)cx, (short)cy);
        win_color(default_attr);
#else
        move(1 + row - top,
             col < screen_w ? col : screen_w - 1);
        refresh();
#endif

        int k = read_key();

        if (k == KEY_F_BASE + 10) {
            if (!dirty || confirm("Discard changes? y: "))
                done = 1;
            continue;
        }

        if (edit && k == KEY_F_BASE + 2) {
            if (save_editor(lines, count, path)) {
                dirty = 0;
                set_status("File saved.");
            } else {
                set_status("Could not save file.");
            }
            continue;
        }

        if (!edit) continue;

        if (k == KEY_UP2) {
            if (row > 0) {
                --row;
                int len = (int)strlen(lines[row]);
                if (col > len) col = len;
            }
        } else if (k == KEY_DOWN2) {
            if (row < count - 1) {
                ++row;
                int len = (int)strlen(lines[row]);
                if (col > len) col = len;
            }
        } else if (k == KEY_LEFT2) {
            if (col > 0) --col;
        } else if (k == KEY_RIGHT2) {
            int len = (int)strlen(lines[row]);
            if (col < len) ++col;
        } else if (k == KEY_PGUP2) {
            row -= 10;
            if (row < 0) row = 0;
            int len = (int)strlen(lines[row]);
            if (col > len) col = len;
        } else if (k == KEY_PGDN2) {
            row += 10;
            if (row >= count) row = count - 1;
            int len = (int)strlen(lines[row]);
            if (col > len) col = len;
        } else if (k == KEY_HOME2) {
            col = 0;
        } else if (k == '\r') {
            if (count < EDIT_LINES) {
                char *s = lines[row];
                size_t len = strlen(s);
                if ((size_t)col > len) col = (int)len;

                char *a = malloc((size_t)col + 1);
                char *b = malloc(len - (size_t)col + 1);

                if (a && b) {
                    memcpy(a, s, (size_t)col);
                    a[col] = '\0';
                    memcpy(b, s + col, len - (size_t)col + 1);

                    free(lines[row]);
                    lines[row] = a;

                    memmove(&lines[row + 2], &lines[row + 1],
                            (size_t)(count - row - 1) * sizeof(char *));
                    lines[row + 1] = b;

                    ++count;
                    ++row;
                    col = 0;
                    dirty = 1;
                } else {
                    free(a);
                    free(b);
                }
            }
        } else if (k == '\b') {
            if (col > 0) {
                char *s = lines[row];
                size_t len = strlen(s);
                memmove(s + col - 1, s + col, len - (size_t)col + 1);
                --col;
                dirty = 1;
            } else if (row > 0) {
                size_t a = strlen(lines[row - 1]);
                size_t b = strlen(lines[row]);
                char *n = malloc(a + b + 1);

                if (n) {
                    memcpy(n, lines[row - 1], a);
                    memcpy(n + a, lines[row], b + 1);

                    free(lines[row - 1]);
                    free(lines[row]);
                    lines[row - 1] = n;

                    memmove(&lines[row], &lines[row + 1],
                            (size_t)(count - row - 1) * sizeof(char *));
                    --count;
                    --row;
                    col = (int)a;
                    dirty = 1;
                }
            }
        } else if (k >= 32 && k < 127) {
            char *s = lines[row];
            size_t len = strlen(s);

            if (len + 1 < EDIT_COLS && (size_t)col <= len) {
                memmove(s + col + 1, s + col, len - (size_t)col + 1);
                s[col] = (char)k;
                ++col;
                dirty = 1;
            }
        }
    }

    for (int i = 0; i < count; ++i)
        free(lines[i]);
    free(lines);
}

static void handle_navigation(int k)
{
    Panel *p = &panels[active_panel];

    if (k == KEY_UP2) {
        if (p->selected > 0) --p->selected;
    } else if (k == KEY_DOWN2) {
        if (p->selected + 1 < p->count) ++p->selected;
    } else if (k == KEY_PGUP2) {
        p->selected -= 10;
        if (p->selected < 0) p->selected = 0;
    } else if (k == KEY_PGDN2) {
        if (p->count > 0) {
            p->selected += 10;
            if (p->selected >= p->count) p->selected = p->count - 1;
        }
    } else if (k == KEY_HOME2) {
        p->selected = 0;
    } else if (k == KEY_END2) {
        if (p->count > 0) p->selected = p->count - 1;
    }
}

int main(void)
{
    init_panels();
    ui_init();

    while (running) {
        draw_ui();
        int k = read_key();

        if (k == KEY_F_BASE + 10 || k == 27) {
            running = 0;
        } else if (k == '\t') {
            active_panel = 1 - active_panel;
        } else if (k == KEY_UP2 || k == KEY_DOWN2 ||
                   k == KEY_PGUP2 || k == KEY_PGDN2 ||
                   k == KEY_HOME2 || k == KEY_END2) {
            handle_navigation(k);
        } else if (k == '\r') {
            action_open();
        } else if (k == '\b') {
            parent_dir(&panels[active_panel]);
        } else if (k == 'n' || k == 'N') {
            action_new_file();
        } else if (k == 'r' || k == 'R') {
            action_rename();
        } else if (k == KEY_F_BASE + 3) {
            action_view();
        } else if (k == KEY_F_BASE + 4) {
            Panel *p = &panels[active_panel];
            if (p->count && !p->items[p->selected].is_dir) {
                char path[PATH_MAX];
                join_path(path, sizeof(path), p->path, p->items[p->selected].name);
                show_file(path, 1);
                load_panel(p);
            }
        } else if (k == KEY_F_BASE + 5) {
            action_copy_move(0);
        } else if (k == KEY_F_BASE + 6) {
            action_copy_move(1);
        } else if (k == KEY_F_BASE + 7) {
            action_mkdir();
        } else if (k == KEY_F_BASE + 8) {
            action_delete();
        } else if (k == KEY_F_BASE + 9) {
            action_search();
        }
    }

    ui_shutdown();
    return 0;
}
'''

cmake = r'''cmake_minimum_required(VERSION 3.16)

project(TextFileManager C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

add_executable(TextFileManager
    src/main.c
)

if(WIN32)
    # Windows uses the native Win32 console API.
    # No curses.h and no PDCurses are required.
    if(MSVC)
        target_compile_options(TextFileManager PRIVATE /W4)
    else()
        target_compile_options(TextFileManager PRIVATE -Wall -Wextra)
    endif()
else()
    find_package(Curses REQUIRED)
    target_include_directories(TextFileManager PRIVATE ${CURSES_INCLUDE_DIRS})
    target_link_libraries(TextFileManager PRIVATE ${CURSES_LIBRARIES})
    target_compile_options(TextFileManager PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()
'''

readme = r'''# Cross-platform TextFileManager

A C11 two-panel text/file manager inspired by Midnight Commander.

## Platforms

- Windows: native Win32 console API, no PDCurses required.
- Linux: ncurses.
- macOS: ncurses supplied by the system.

## Features

- Two file panels
- Arrow-key navigation
- Tab switches panels
- Enter opens directories or edits text files
- Backspace goes to parent
- F3 viewer
- F4 editor
- F5 copy
- F6 move
- F7 create directory
- F8 delete
- F9 search
- F10 exit
- N create file
- R rename

## Windows / MinGW

From the project directory:

    cmake -S . -B build -G "MinGW Makefiles"
    cmake --build build
    .\build\TextFileManager.exe

If your VS Code CMake Tools extension is installed, it can configure and build the project as well.

## Linux

Install ncurses development files, for example on Debian/Ubuntu:

    sudo apt install build-essential cmake libncurses-dev

Then:

    cmake -S . -B build
    cmake --build build
    ./build/TextFileManager

## macOS

Install CMake if needed:

    brew install cmake

Then:

    cmake -S . -B build
    cmake --build build
    ./build/TextFileManager

The source intentionally uses only standard C plus platform-specific console/file APIs.
'''

tasks = r'''{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "Configure CMake",
            "type": "shell",
            "command": "cmake",
            "args": [
                "-S", "${workspaceFolder}",
                "-B", "${workspaceFolder}/build",
                "-G", "MinGW Makefiles"
            ],
            "problemMatcher": []
        },
        {
            "label": "Build TextFileManager",
            "type": "shell",
            "command": "cmake",
            "args": [
                "--build", "${workspaceFolder}/build"
            ],
            "group": {
                "kind": "build",
                "isDefault": true
            },
            "problemMatcher": ["$gcc"]
        }
    ]
}
'''

launch = r'''{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Run TextFileManager",
            "type": "cppdbg",
            "request": "launch",
            "program": "${workspaceFolder}/build/TextFileManager.exe",
            "cwd": "${workspaceFolder}",
            "externalConsole": true,
            "MIMode": "gdb",
            "miDebuggerPath": "gdb.exe",
            "preLaunchTask": "Build TextFileManager"
        }
    ]
}
'''

(root / "CMakeLists.txt").write_text(cmake, encoding="utf-8", newline="\n")
(src / "main.c").write_text(main_c, encoding="utf-8", newline="\n")
(root / "README.md").write_text(readme, encoding="utf-8", newline="\n")
(vscode / "tasks.json").write_text(tasks, encoding="utf-8", newline="\n")
(vscode / "launch.json").write_text(launch, encoding="utf-8", newline="\n")

print(f"Created clean cross-platform project: {root}")
print(f"Source: {src / 'main.c'}")
print(f"CMake: {root / 'CMakeLists.txt'}")
