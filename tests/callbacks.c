// Exercise C by-value aggregate inputs and returns through the typed bridge.
#include "../src/callbacks.c"
#include <assert.h>

static bool action(void *app, const ghostty_target_s *target, const ghostty_action_s *value) {
    assert(app == (void *)17);
    return target->tag == GHOSTTY_TARGET_SURFACE && value->tag == GHOSTTY_ACTION_PWD;
}
static void insert(void *self, void *cmd, void *text, const JimRange *range) {
    assert(self == (void *)1 && cmd == (void *)2 && text == (void *)3);
    assert(range->location == 7 && range->length == 9);
}
static void marked(void *self, void *cmd, void *text, const JimRange *a, const JimRange *b) {
    insert(self, cmd, text, a);
    assert(b->location == 11 && b->length == 13);
}
static void *substring(void *self, void *cmd, const JimRange *range, JimRange *actual) {
    assert(self == (void *)1 && cmd == (void *)2);
    *actual = *range;
    return (void *)23;
}
static uint64_t index_at(void *self, void *cmd, const CGPoint *point) {
    assert(self == (void *)1 && cmd == (void *)2);
    assert(point->x == 12.5 && point->y == 24.5);
    return 31;
}
static void first_rect(void *self, void *cmd, const JimRange *range, JimRange *actual,
                       CGRect *out) {
    substring(self, cmd, range, actual);
    *out = (CGRect){{1.25, 2.5}, {3.75, 4.5}};
}
static void range_out(void *self, void *cmd, JimRange *out) {
    assert(self == (void *)1 && cmd == (void *)2);
    *out = (JimRange){17, 19};
}
int main(void) {
    jim_callbacks_init(action, insert, marked, substring, index_at, first_rect, range_out,
                       range_out);
    ghostty_target_s target = {.tag = GHOSTTY_TARGET_SURFACE};
    ghostty_action_s value = {.tag = GHOSTTY_ACTION_PWD};
    assert(jim_terminal_action((void *)17, target, value));
    JimRange a = {7, 9}, b = {11, 13}, actual;
    jim_terminal_insert((void *)1, (void *)2, (void *)3, a);
    jim_terminal_set_marked((void *)1, (void *)2, (void *)3, a, b);
    assert(jim_terminal_substring((void *)1, (void *)2, a, &actual) == (void *)23);
    assert(actual.location == 7 && actual.length == 9);
    assert(jim_terminal_character_index((void *)1, (void *)2, (CGPoint){12.5, 24.5}) == 31);
    CGRect rect = jim_terminal_first_rect((void *)1, (void *)2, a, &actual);
    assert(rect.origin.x == 1.25 && rect.origin.y == 2.5 && rect.size.width == 3.75 &&
           rect.size.height == 4.5);
    a = jim_terminal_marked_range((void *)1, (void *)2);
    b = jim_terminal_selected_range((void *)1, (void *)2);
    assert(a.location == 17 && a.length == 19 && b.location == 17 && b.length == 19);
    return 0;
}
