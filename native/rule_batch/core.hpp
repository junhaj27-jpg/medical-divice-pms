#pragma once

#include <array>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <unordered_set>
#include <vector>
#include <nlohmann/json.hpp>

namespace pms_batch {
using Json = nlohmann::json;
inline constexpr std::size_t max_bytes = 16 * 1024 * 1024;
inline constexpr std::size_t max_cases = 10'000;

struct InputError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct Rule {
    std::string id;
    int version;
    std::string basis;
    Json conditions;
    std::optional<std::string> device;
    bool example;
    std::string unit, day_type, timezone, deadline_time;
    std::optional<int> days;
    std::optional<bool> include_start;
    bool standard_weekend;
    std::unordered_set<int> holidays;
    std::optional<int> verified_from, verified_until, checked_on;
};

struct Case {
    std::string id;
    std::optional<std::string> device;
    bool example;
    Json facts, bases, business_dates;
    std::array<std::optional<std::string>, 2> holds;
};

struct Batch {
    std::string market;
    std::array<Rule, 2> rules;
    std::vector<Case> cases;
};

Batch parse(std::string_view input);
Json evaluate(const Batch& batch);
std::string run_json(std::string_view input);
Json error(const char* code, const std::string& message);
}
