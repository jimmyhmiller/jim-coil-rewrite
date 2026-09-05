#include "../vendor/ghostty.h"
#include <stddef.h>
// These match the audited Coil declarations in src/ghostty.coil.
_Static_assert(sizeof(ghostty_surface_config_s) == 88, "surface config size");
_Static_assert(_Alignof(ghostty_surface_config_s) == 8, "surface config alignment");
_Static_assert(offsetof(ghostty_surface_config_s, platform) == 8, "platform union");
_Static_assert(offsetof(ghostty_surface_config_s, userdata) == 16, "userdata");
_Static_assert(offsetof(ghostty_surface_config_s, scale_factor) == 24, "scale");
_Static_assert(offsetof(ghostty_surface_config_s, working_directory) == 40, "cwd");
_Static_assert(offsetof(ghostty_surface_config_s, context) == 84, "context");
_Static_assert(sizeof(ghostty_input_key_s) == 32, "key size");
_Static_assert(offsetof(ghostty_input_key_s, text) == 16, "key text");
_Static_assert(offsetof(ghostty_input_key_s, composing) == 28, "key composing");
_Static_assert(sizeof(ghostty_runtime_config_s) == 64, "runtime size");
_Static_assert(offsetof(ghostty_runtime_config_s, wakeup_cb) == 16, "wakeup");
_Static_assert(sizeof(ghostty_target_s) == 16, "target ABI");
_Static_assert(sizeof(ghostty_action_s) == 32, "action ABI");
_Static_assert(_Alignof(ghostty_action_s) == 8, "action alignment");
int main(void) { return 0; }
