#include "core.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>

using Clock = std::chrono::steady_clock;
using namespace pms_batch;

std::string read(std::istream& stream) {
    std::string data;
    char buffer[8192];
    while (stream.read(buffer, sizeof(buffer)) || stream.gcount()) {
        data.append(buffer, static_cast<std::size_t>(stream.gcount()));
        if (data.size() > max_bytes) throw InputError("input exceeds 16 MiB");
    }
    if (!stream.eof() || stream.bad()) throw std::ios_base::failure("cannot read input");
    return data;
}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    bool timings = false;
    int arg = 1;
    if (argc > 1 && std::filesystem::path(argv[1]) == "--timings") { timings = true; ++arg; }
    try {
        if (argc - arg > 1) throw InputError("usage: pms-rule-batch [--timings] [FILE|-]");
        std::ifstream file;
        std::istream* input = &std::cin;
        if (argc > arg && std::filesystem::path(argv[arg]) != "-") {
            file.open(std::filesystem::path(argv[arg]), std::ios::binary);
            if (!file) throw std::ios_base::failure("cannot open input");
            input = &file;
        }
        const auto start = Clock::now();
        auto batch = parse(read(*input));
        const auto prepared = Clock::now();
        auto result = evaluate(batch);
        const auto calculated = Clock::now();
        std::cout << result.dump() << '\n';
        std::cout.flush();
        if (!std::cout) throw std::ios_base::failure("cannot write result");
        if (timings) {
            auto ms = [](auto span) { return std::chrono::duration<double, std::milli>(span).count(); };
            std::cerr << Json{{"prepare_ms", ms(prepared - start)}, {"compute_ms", ms(calculated - prepared)},
                              {"write_ms", ms(Clock::now() - calculated)}}.dump() << '\n';
        }
    } catch (const InputError& exc) {
        std::cerr << error("invalid_input", exc.what()).dump() << '\n';
        return 2;
    } catch (const std::ios_base::failure&) {
        std::cerr << error("io_error", "cannot open, read or write a stream").dump() << '\n';
        return 3;
    } catch (const std::exception&) {
        std::cerr << error("internal_error", "unexpected engine failure").dump() << '\n';
        return 4;
    }
}
