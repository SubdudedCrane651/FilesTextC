#include <stdio.h>
#include <windows.h>
#include <dirent.h>
#include <string.h>
#include <sys/stat.h>

#define MAX_ITEMS 2048
#define PATH_MAX_LEN 1024

char items[MAX_ITEMS][PATH_MAX_LEN];
int count = 0;

int main() {
    char path[PATH_MAX_LEN];
    GetCurrentDirectoryA(PATH_MAX_LEN, path);

    printf("Listing directory: %s\n", path);

    DIR *d = opendir(path);
    if (!d) {
        printf("Cannot open directory.\n");
        return 1;
    }

    struct dirent *ent;
    while ((ent = readdir(d)) != NULL && count < MAX_ITEMS) {
        strcpy(items[count++], ent->d_name);
    }
    closedir(d);

    printf("Found %d items:\n", count);
    for (int i = 0; i < count; i++) {
        printf("  %s\n", items[i]);
    }

    printf("\nPress Enter to exit.\n");
    getchar();
    return 0;
}
