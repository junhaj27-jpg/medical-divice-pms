#include "core.hpp"
#include <chrono>
#include <pybind11/pybind11.h>

namespace py = pybind11;
using namespace pms_batch;

PYBIND11_MODULE(pms_rule_batch, module) {
    py::register_exception<InputError>(module, "InputError", PyExc_ValueError);
    module.def("run_json", [](const std::string& input) {
        py::gil_scoped_release unlocked;
        return run_json(input);
    });
    module.def("run_timed", [](const std::string& input) {
        using Clock = std::chrono::steady_clock;
        std::string output;
        double compute_ms;
        {
            py::gil_scoped_release unlocked;
            auto batch = parse(input);
            const auto start = Clock::now();
            auto result = evaluate(batch);
            compute_ms = std::chrono::duration<double, std::milli>(Clock::now() - start).count();
            output = result.dump();
        }
        return py::make_tuple(output, compute_ms);
    });
}
