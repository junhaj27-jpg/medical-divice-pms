#include "core.hpp"

#include <algorithm>
#include <charconv>
#include <cstdio>
#include <initializer_list>

namespace pms_batch {
namespace {
constexpr std::array<const char*, 4> bases{"OCCURRED", "REPORTED", "AWARE", "CUSTOM"};

bool in(std::string_view value, std::initializer_list<std::string_view> choices) {
    return std::find(choices.begin(), choices.end(), value) != choices.end();
}

void require(bool condition, const char* message) {
    if (!condition) throw InputError(message);
}

int digits(std::string_view s) {
    int value = 0;
    const auto parsed = std::from_chars(s.data(), s.data() + s.size(), value);
    require(!s.empty() && std::all_of(s.begin(), s.end(), [](char c) { return c >= '0' && c <= '9'; })
            && parsed.ec == std::errc{} && parsed.ptr == s.data() + s.size(), "invalid date or time");
    return value;
}

int year_start(int year) {
    int previous = year - 1;
    return 365 * previous + previous / 4 - previous / 100 + previous / 400;
}

int month_length(int year, int month) {
    constexpr int lengths[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    bool leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    return lengths[month - 1] + (month == 2 && leap ? 1 : 0);
}

int ordinal(std::string_view date) {
    require(date.size() == 10 && date[4] == '-' && date[7] == '-', "expected YYYY-MM-DD");
    int year = digits(date.substr(0, 4));
    int month = digits(date.substr(5, 2));
    int day = digits(date.substr(8, 2));
    require(year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= month_length(year, month),
            "date outside Gregorian calendar");
    int result = year_start(year) + day - 1;
    for (int m = 1; m < month; ++m) result += month_length(year, m);
    return result;
}

std::string date_string(int ordinal_day) {
    int low = 1, high = 10000;
    while (high - low > 1) {
        int mid = (low + high) / 2;
        if (year_start(mid) <= ordinal_day) low = mid;
        else high = mid;
    }
    int day = ordinal_day - year_start(low), month = 1;
    while (day >= month_length(low, month)) day -= month_length(low, month++);
    char value[11];
    std::snprintf(value, sizeof(value), "%04d-%02d-%02d", low, month, day + 1);
    return value;
}

void check_time(std::string_view time) {
    require(time.size() == 8 && time[2] == ':' && time[5] == ':'
            && digits(time.substr(0, 2)) <= 23 && digits(time.substr(3, 2)) <= 59
            && digits(time.substr(6, 2)) <= 59, "deadline_time must be HH:MM:SS");
}

std::string string(const Json& value, std::size_t limit = 128) {
    require(value.is_string(), "expected string");
    auto result = value.get<std::string>();
    require(!result.empty() && result.size() <= limit, "invalid string length");
    return result;
}

int integer(const Json& value, int minimum, int maximum) {
    require(value.is_number_integer() && value >= minimum && value <= maximum, "integer outside allowed range");
    return value.get<int>();
}

bool boolean(const Json& value) {
    require(value.is_boolean(), "expected boolean");
    return value.get<bool>();
}

template <class Parser>
auto optional(const Json& value, Parser parse) -> std::optional<decltype(parse(value))> {
    return value.is_null() ? std::nullopt : std::optional{parse(value)};
}

const Json& field(const Json& obj, const char* key) {
    require(obj.is_object(), "expected object");
    const auto it = obj.find(key);
    static const Json null;
    return it == obj.end() ? null : *it;
}

void check_facts(const Json& object, bool nullable) {
    require(object.is_object(), "facts and conditions must be objects");
    for (auto it = object.begin(); it != object.end(); ++it) {
        require(in(it.key(), {"complaint_type", "risk_level", "serious"}), "unknown fact or condition");
        if (it->is_null() && nullable) continue;
        if (it.key() == "serious") boolean(*it);
        else {
            auto value = string(*it, 200);
            if (it.key() == "risk_level") {
                require(in(value, {"LOW", "MEDIUM", "HIGH", "CRITICAL"}), "unknown risk level");
            }
        }
    }
}

void check_timestamp(std::string_view value) {
    require(value.size() >= 20 && value[10] == 'T', "expected timestamp with UTC offset");
    ordinal(value.substr(0, 10));
    check_time(value.substr(11, 8));
    value.remove_prefix(19);
    if (!value.empty() && value.front() == '.') {
        value.remove_prefix(1);
        auto end = value.find_first_not_of("0123456789");
        require(end >= 1 && end <= 6, "invalid fractional second");
        value.remove_prefix(end);
    }
    if (value == "Z") return;
    require(value.size() == 6 && (value[0] == '+' || value[0] == '-') && value[3] == ':'
            && digits(value.substr(1, 2)) <= 23 && digits(value.substr(4, 2)) <= 59,
            "expected timestamp with UTC offset");
}

void check_bases(const Json& object, bool dates_only) {
    require(object.is_object(), "bases and business_dates must be objects");
    for (auto it = object.begin(); it != object.end(); ++it) {
        require(std::find(bases.begin(), bases.end(), it.key()) != bases.end(), "unknown basis");
        if (it->is_null()) continue;
        auto value = string(*it);
        if (dates_only || value.size() == 10) ordinal(value);
        else check_timestamp(value);
    }
}

Rule parse_rule(const Json& input, const std::string& market) {
    require(string(input.at("market")) == market, "rule market must match batch");
    Rule rule{};
    rule.id = string(input.at("id"));
    rule.version = integer(input.at("version"), 1, 2147483647);
    rule.basis = optional(field(input, "basis"), [](const Json& j) { return string(j); }).value_or("");
    rule.conditions = input.at("conditions");
    check_facts(rule.conditions, false);
    rule.device = optional(field(input, "device"), [](const Json& j) { return string(j); });
    rule.example = boolean(input.at("example"));
    rule.unit = string(input.at("unit"));
    rule.day_type = string(input.at("day_type"));
    rule.timezone = string(input.at("timezone"));
    rule.days = optional(field(input, "days"), [](const Json& j) { return integer(j, 0, 3660); });
    rule.include_start = optional(field(input, "include_start"), boolean);
    const auto& clock = field(input, "deadline_time");
    if (!clock.is_null()) {
        rule.deadline_time = string(clock);
        check_time(rule.deadline_time);
    }
    const auto& calendar = input.at("calendar");
    const auto& weekend = calendar.at("weekend");
    require(weekend.is_array() && weekend.size() <= 7, "weekend must contain weekday numbers 0–6");
    std::unordered_set<int> weekdays;
    for (const auto& value : weekend) require(weekdays.insert(integer(value, 0, 6)).second, "duplicate weekday");
    rule.standard_weekend = weekdays == std::unordered_set<int>{5, 6};
    const auto& holidays = calendar.at("holidays");
    require(holidays.is_array() && holidays.size() <= max_cases, "invalid holiday list");
    for (const auto& day : holidays) {
        require(rule.holidays.insert(ordinal(string(day))).second, "duplicate holiday");
    }
    auto parse_date = [](const Json& value) { return ordinal(string(value)); };
    rule.verified_from = optional(field(calendar, "verified_from"), parse_date);
    rule.verified_until = optional(field(calendar, "verified_until"), parse_date);
    rule.checked_on = optional(field(calendar, "checked_on"), parse_date);
    require(!rule.verified_from || !rule.verified_until || *rule.verified_from <= *rule.verified_until,
            "invalid holiday coverage range");
    return rule;
}

Case parse_case(const Json& input) {
    Case entry{};
    entry.id = string(input.at("id"));
    entry.device = optional(field(input, "device"), [](const Json& j) { return string(j); });
    entry.example = boolean(input.at("example"));
    entry.facts = input.at("facts");
    entry.bases = input.at("bases");
    entry.business_dates = input.value("business_dates", Json::object());
    check_facts(entry.facts, true);
    check_bases(entry.bases, false);
    check_bases(entry.business_dates, true);
    const auto& holds = field(input, "holds");
    if (!holds.is_null()) {
        require(holds.is_array() && holds.size() == 2, "holds must contain two entries");
        for (int i = 0; i < 2; ++i) {
            entry.holds[i] = optional(holds[i], [](const Json& j) {
                auto reason = string(j);
                require(in(reason, {"source_unverified", "scope_mismatch"}), "unknown precheck hold");
                return reason;
            });
        }
    }
    return entry;
}

struct Result {
    const char* decision = "HOLD";
    const char* reason = "missing_input";
    std::optional<std::string> basis, due, due_at;
    std::optional<int> due_day;
};

Result status(const char* decision, const char* reason) {
    Result result;
    result.decision = decision;
    result.reason = reason;
    return result;
}

Result calculate(const Rule& rule, const Case& entry, const std::optional<std::string>& precheck) {
    if ((rule.device && rule.device != entry.device) || rule.example != entry.example)
        return status("HOLD", "scope_mismatch");
    if (precheck) return status("HOLD", *precheck == "source_unverified" ? "source_unverified" : "scope_mismatch");
    for (const auto& [key, expected] : rule.conditions.items()) {
        if (field(entry.facts, key.c_str()).is_null()) return status("HOLD", "missing_input");
    }
    for (const auto& [key, expected] : rule.conditions.items()) {
        if (entry.facts.at(key) != expected) return status("NO_MATCH", "scope_mismatch");
    }
    if (std::find(bases.begin(), bases.end(), rule.basis) == bases.end()) return status("HOLD", "missing_input");
    const auto& basis = field(entry.bases, rule.basis.c_str());
    if (basis.is_null()) return status("HOLD", "missing_input");
    const auto& value = basis.get_ref<const std::string&>();
    if (rule.unit != "DAYS" || !in(rule.day_type, {"CALENDAR", "BUSINESS"})
        || (rule.day_type == "BUSINESS" && !rule.standard_weekend))
        return status("unsupported", "unsupported_method");
    if (value.size() != 10) return status("unsupported", "unsupported_timestamp");
    int start = ordinal(value);
    const char* offset = nullptr;
    if (in(rule.timezone, {"UTC", "Etc/UTC"})) offset = "+00:00";
    if (rule.timezone == "Asia/Seoul" && start >= year_start(2000)) offset = "+09:00";
    if (!offset) return status("unsupported", "unsupported_timezone");
    const auto& business_date = field(entry.business_dates, rule.basis.c_str());
    if (!business_date.is_null() && business_date != basis) return status("HOLD", "date_mismatch");

    Result result;
    result.basis = value;
    result.reason = "calculation_unverified";
    if (!rule.days || !rule.include_start || rule.deadline_time.empty()) return result;
    const bool business = rule.day_type == "BUSINESS";
    auto covered = [&](int day) {
        return rule.verified_from && rule.verified_until && rule.checked_on
            && *rule.verified_from <= day && day <= *rule.verified_until;
    };
    int day = start;
    if (business && !covered(day)) return result;
    int remaining = *rule.days;
    if (remaining && !*rule.include_start) ++day;
    while (remaining) {
        if (day >= year_start(10000) || (business && !covered(day))) return result;
        if (!business || (day % 7 < 5 && !rule.holidays.count(day))) --remaining;
        if (remaining) ++day;
    }
    result.decision = "REPORT";
    result.reason = "rule_match";
    result.due_day = day;
    result.due = date_string(day);
    result.due_at = *result.due + "T" + rule.deadline_time + offset;
    return result;
}

template <class T>
Json nullable(const std::optional<T>& value) {
    return value ? Json(*value) : Json(nullptr);
}

Json to_json(const Result& result, const Rule& rule) {
    return {{"decision", result.decision}, {"reason", result.reason},
            {"basis_date", nullable(result.basis)}, {"due_date", nullable(result.due)},
            {"due_at", nullable(result.due_at)}, {"rule_id", rule.id}, {"version", rule.version}};
}

Json differences(const Result& before, const Result& after) {
    const std::string_view left = before.decision, right = after.decision;
    const bool review = in(left, {"HOLD", "unsupported"}) || in(right, {"HOLD", "unsupported"});
    Json changes = Json::array();
    if (!review && left != right) changes.push_back("decision_changed");
    std::optional<int> delta;
    if (before.due_day && after.due_day) {
        delta = *after.due_day - *before.due_day;
        if (*delta < 0) changes.push_back("earlier");
        else if (*delta > 0) changes.push_back("later");
        else if (before.due_at != after.due_at) changes.push_back("time_changed");
    } else if (before.due_day) changes.push_back("deadline_removed");
    else if (after.due_day) changes.push_back("deadline_added");
    if (review) changes.push_back("review_required");
    if (changes.empty()) changes.push_back("unchanged");
    return {{"changes", changes}, {"delta_days", nullable(delta)}};
}
}

Batch parse(std::string_view input) {
    require(input.size() <= max_bytes, "input exceeds 16 MiB");
    try {
        const auto json = Json::parse(input, [](int depth, Json::parse_event_t, Json&) {
            require(depth < 32, "JSON nesting limit exceeded");
            return true;
        });
        require(integer(json.at("schema_version"), 1, 1) == 1, "unsupported schema version");
        auto market = string(json.at("market"));
        require(in(market, {"KR", "US", "DE", "FR", "ES", "IT"}), "unknown market");
        const auto& rules = json.at("rules");
        require(rules.is_array() && rules.size() == 2, "exactly two rule versions are required");
        Batch batch{market, {parse_rule(rules[0], market), parse_rule(rules[1], market)}, {}};
        const auto& cases = json.at("cases");
        require(cases.is_array() && !cases.empty() && cases.size() <= max_cases, "expected 1–10000 cases");
        std::unordered_set<std::string> ids;
        batch.cases.reserve(cases.size());
        for (const auto& item : cases) {
            auto entry = parse_case(item);
            require(ids.insert(entry.id).second, "duplicate case id");
            batch.cases.push_back(std::move(entry));
        }
        return batch;
    } catch (const Json::exception&) {
        // Parser messages can quote input. Do not copy case data into diagnostics.
        throw InputError("malformed JSON or missing/invalid field");
    }
}

Json evaluate(const Batch& batch) {
    Json rows = Json::array();
    auto& array = rows.get_ref<Json::array_t&>();
    array.reserve(batch.cases.size());
    for (const auto& entry : batch.cases) {
        auto before = calculate(batch.rules[0], entry, entry.holds[0]);
        auto after = calculate(batch.rules[1], entry, entry.holds[1]);
        auto row = differences(before, after);
        row["case_id"] = entry.id;
        row["baseline"] = to_json(before, batch.rules[0]);
        row["proposed"] = to_json(after, batch.rules[1]);
        array.push_back(std::move(row));
    }
    return {{"schema_version", 1}, {"market", batch.market}, {"results", std::move(rows)}};
}

std::string run_json(std::string_view input) {
    return evaluate(parse(input)).dump();
}

Json error(const char* code, const std::string& message) {
    return {{"schema_version", 1}, {"error", {{"code", code}, {"message", message}}}};
}
}
