// The C ABI boundary for native callbacks with by-value aggregate arguments.
// Coil functions receive borrowed struct pointers. Keep that conversion here;
// never reinterpret the native callback as a Coil reference-convention function.
#include "../vendor/ghostty.h"
#include <CoreFoundation/CoreFoundation.h>
#include <CoreGraphics/CoreGraphics.h>
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint64_t location, length;
} JimRange;
static bool (*action_callback)(void *, const ghostty_target_s *, const ghostty_action_s *);
static void (*insert_callback)(void *, void *, void *, const JimRange *);
static void (*marked_callback)(void *, void *, void *, const JimRange *, const JimRange *);
static void *(*substring_callback)(void *, void *, const JimRange *, JimRange *);
static uint64_t (*index_callback)(void *, void *, const CGPoint *);
static void (*rect_callback)(void *, void *, const JimRange *, JimRange *, CGRect *);
static void (*marked_range_callback)(void *, void *, JimRange *);
static void (*selected_range_callback)(void *, void *, JimRange *);

void jim_callbacks_init(bool (*action)(void *, const ghostty_target_s *, const ghostty_action_s *),
                        void (*insert)(void *, void *, void *, const JimRange *),
                        void (*marked)(void *, void *, void *, const JimRange *, const JimRange *),
                        void *(*substring)(void *, void *, const JimRange *, JimRange *),
                        uint64_t (*index)(void *, void *, const CGPoint *),
                        void (*rect)(void *, void *, const JimRange *, JimRange *, CGRect *),
                        void (*marked_range)(void *, void *, JimRange *),
                        void (*selected_range)(void *, void *, JimRange *)) {
    action_callback = action;
    insert_callback = insert;
    marked_callback = marked;
    substring_callback = substring;
    index_callback = index;
    rect_callback = rect;
    marked_range_callback = marked_range;
    selected_range_callback = selected_range;
}
bool jim_terminal_action(void *app, ghostty_target_s target, ghostty_action_s value) {
    return action_callback(app, &target, &value);
}
void jim_terminal_insert(void *self, void *cmd, void *text, JimRange range) {
    insert_callback(self, cmd, text, &range);
}
void jim_terminal_set_marked(void *self, void *cmd, void *text, JimRange selected,
                             JimRange replacement) {
    marked_callback(self, cmd, text, &selected, &replacement);
}
void *jim_terminal_substring(void *self, void *cmd, JimRange range, JimRange *actual) {
    return substring_callback(self, cmd, &range, actual);
}
uint64_t jim_terminal_character_index(void *self, void *cmd, CGPoint point) {
    return index_callback(self, cmd, &point);
}
CGRect jim_terminal_first_rect(void *self, void *cmd, JimRange range, JimRange *actual) {
    CGRect result;
    rect_callback(self, cmd, &range, actual, &result);
    return result;
}

JimRange jim_terminal_marked_range(void *self, void *cmd) {
    JimRange result;
    marked_range_callback(self, cmd, &result);
    return result;
}
JimRange jim_terminal_selected_range(void *self, void *cmd) {
    JimRange result;
    selected_range_callback(self, cmd, &result);
    return result;
}
