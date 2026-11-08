#include "core.hpp"
#include <emscripten/bind.h>

std::string compare(const std::string& input) {
    try {
        return pms_batch::run_json(input);
    } catch (const pms_batch::InputError& exc) {
        return pms_batch::error("invalid_input", exc.what()).dump();
    } catch (const std::exception&) {
        return pms_batch::error("internal_error", "unexpected engine failure").dump();
    }
}

EMSCRIPTEN_BINDINGS(rule_batch) {
    emscripten::function("runJson", &compare);
}
