// SPDX-License-Identifier: Apache-2.0
#include "akvc/macos_ipc.h"

#include <cstdlib>
#include <cstring>
#include <fstream>
#include <pwd.h>
#include <string>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

static bool akvc_macos_is_valid_shm_name(const char* candidate) {
    if (candidate == nullptr || candidate[0] == '\0') {
        return false;
    }
    if (candidate[0] != '/') {
        return false;
    }
    return std::strlen(candidate) < sizeof(((akvc_macos_ring_descriptor_t*)0)->shm_name);
}

static bool akvc_macos_is_valid_device_name(const char* candidate) {
    return candidate != nullptr && candidate[0] != '\0';
}

static void akvc_macos_trim_trailing_ascii_whitespace(std::string* value) {
    if (value == nullptr) {
        return;
    }
    while (!value->empty()) {
        char tail = value->back();
        if (tail != '\r' && tail != '\n' && tail != ' ' && tail != '\t') {
            break;
        }
        value->pop_back();
    }
}

static int akvc_macos_parse_bool_text(const char* candidate) {
    if (candidate == nullptr || candidate[0] == '\0') {
        return -1;
    }

    if (std::strcmp(candidate, "1") == 0
        || std::strcmp(candidate, "true") == 0
        || std::strcmp(candidate, "TRUE") == 0
        || std::strcmp(candidate, "yes") == 0
        || std::strcmp(candidate, "YES") == 0
        || std::strcmp(candidate, "on") == 0
        || std::strcmp(candidate, "ON") == 0) {
        return 1;
    }

    if (std::strcmp(candidate, "0") == 0
        || std::strcmp(candidate, "false") == 0
        || std::strcmp(candidate, "FALSE") == 0
        || std::strcmp(candidate, "no") == 0
        || std::strcmp(candidate, "NO") == 0
        || std::strcmp(candidate, "off") == 0
        || std::strcmp(candidate, "OFF") == 0) {
        return 0;
    }

    return -1;
}

static std::string akvc_macos_current_user_home_directory(void) {
    struct passwd* user = getpwuid(getuid());
    if (user != nullptr && user->pw_dir != nullptr && user->pw_dir[0] != '\0') {
        return std::string(user->pw_dir);
    }
    const char* home = std::getenv("HOME");
    if (home != nullptr && home[0] != '\0') {
        return std::string(home);
    }
    return std::string();
}

static std::string akvc_macos_console_user_home_directory(void) {
    struct stat console_stat = {};
    if (stat("/dev/console", &console_stat) != 0) {
        return std::string();
    }

    struct passwd* console_user = getpwuid(console_stat.st_uid);
    if (console_user != nullptr && console_user->pw_dir != nullptr && console_user->pw_dir[0] != '\0') {
        return std::string(console_user->pw_dir);
    }
    return std::string();
}

static std::string akvc_macos_default_shared_state_dir_path(void) {
    const char* explicit_dir = std::getenv(AKVC_MACOS_SHARED_STATE_DIR_ENV);
    if (explicit_dir != nullptr && explicit_dir[0] != '\0') {
        return std::string(explicit_dir);
    }

    // Camera Extensions run as a CMIO helper account rather than the logged-in
    // desktop user, so prefer the console user's home to keep both processes
    // pointed at the same shared-state directory.
    std::string home = akvc_macos_console_user_home_directory();
    if (home.empty()) {
        home = akvc_macos_current_user_home_directory();
    }
    if (home.empty()) {
        return std::string("/private/tmp/akvc-shared");
    }

    std::string path(home);
    path += "/";
    path += AKVC_MACOS_SHARED_STATE_DIR_SUFFIX;
    return path;
}

static std::string akvc_macos_default_shm_name_file_path(void) {
    std::string path = akvc_macos_default_shared_state_dir_path();
    path += "/";
    path += AKVC_MACOS_SHM_NAME_FILE_NAME;
    return path;
}

static std::string akvc_macos_default_device_name_file_path(void) {
    std::string path = akvc_macos_default_shared_state_dir_path();
    path += "/";
    path += AKVC_MACOS_DEVICE_NAME_FILE_NAME;
    return path;
}

static std::string akvc_macos_default_demo_mode_file_path(void) {
    std::string path = akvc_macos_default_shared_state_dir_path();
    path += "/";
    path += AKVC_MACOS_DEMO_MODE_FILE_NAME;
    return path;
}

static std::string akvc_macos_resolved_shm_name_file_path(void) {
    const char* explicit_path = std::getenv(AKVC_MACOS_SHM_NAME_FILE_ENV);
    if (explicit_path != nullptr && explicit_path[0] != '\0') {
        return std::string(explicit_path);
    }
    return akvc_macos_default_shm_name_file_path();
}

static std::string akvc_macos_resolved_device_name_file_path(void) {
    const char* explicit_path = std::getenv(AKVC_MACOS_DEVICE_NAME_FILE_ENV);
    if (explicit_path != nullptr && explicit_path[0] != '\0') {
        return std::string(explicit_path);
    }
    return akvc_macos_default_device_name_file_path();
}

static std::string akvc_macos_resolved_demo_mode_file_path(void) {
    const char* explicit_path = std::getenv(AKVC_MACOS_DEMO_MODE_FILE_ENV);
    if (explicit_path != nullptr && explicit_path[0] != '\0') {
        return std::string(explicit_path);
    }
    return akvc_macos_default_demo_mode_file_path();
}

static std::string akvc_macos_read_shm_name_from_file(void) {
    std::string path = akvc_macos_resolved_shm_name_file_path();
    if (path.empty()) {
        return std::string();
    }

    std::ifstream stream(path);
    if (!stream.good()) {
        return std::string();
    }

    std::string line;
    std::getline(stream, line);
    akvc_macos_trim_trailing_ascii_whitespace(&line);
    return line;
}

static std::string akvc_macos_read_device_name_from_file(void) {
    std::string path = akvc_macos_resolved_device_name_file_path();
    if (path.empty()) {
        return std::string();
    }

    std::ifstream stream(path);
    if (!stream.good()) {
        return std::string();
    }

    std::string line;
    std::getline(stream, line);
    akvc_macos_trim_trailing_ascii_whitespace(&line);
    return line;
}

static std::string akvc_macos_read_demo_mode_from_file(void) {
    std::string path = akvc_macos_resolved_demo_mode_file_path();
    if (path.empty()) {
        return std::string();
    }

    std::ifstream stream(path);
    if (!stream.good()) {
        return std::string();
    }

    std::string line;
    std::getline(stream, line);
    akvc_macos_trim_trailing_ascii_whitespace(&line);
    return line;
}

static const char* akvc_macos_resolved_shm_name(void) {
    const char* override_name = std::getenv(AKVC_MACOS_SHM_NAME_ENV);
    if (akvc_macos_is_valid_shm_name(override_name)) {
        return override_name;
    }

    static std::string file_override;
    file_override = akvc_macos_read_shm_name_from_file();
    if (akvc_macos_is_valid_shm_name(file_override.c_str())) {
        return file_override.c_str();
    }

    return AKVC_POSIX_SHM_NAME;
}

const char* akvc_macos_resolved_device_name(void) {
    const char* override_name = std::getenv(AKVC_MACOS_DEVICE_NAME_ENV);
    if (akvc_macos_is_valid_device_name(override_name)) {
        return override_name;
    }

    static std::string file_override;
    file_override = akvc_macos_read_device_name_from_file();
    if (akvc_macos_is_valid_device_name(file_override.c_str())) {
        return file_override.c_str();
    }

    return "AK Virtual Camera";
}

int akvc_macos_demo_mode_enabled(void) {
    int environment_value = akvc_macos_parse_bool_text(std::getenv(AKVC_MACOS_DEMO_MODE_ENV));
    if (environment_value >= 0) {
        return environment_value;
    }

    static std::string file_override;
    file_override = akvc_macos_read_demo_mode_from_file();
    int file_value = akvc_macos_parse_bool_text(file_override.c_str());
    if (file_value >= 0) {
        return file_value;
    }

    return 0;
}

void akvc_macos_ring_descriptor_default(akvc_macos_ring_descriptor_t* out_desc) {
    if (out_desc == nullptr) {
        return;
    }
    out_desc->slot_count = AKVC_RING_SLOTS;
    out_desc->slot_size = AKVC_DEFAULT_SLOT_SIZE;
    std::memset(out_desc->shm_name, 0, sizeof(out_desc->shm_name));
    std::strncpy(out_desc->shm_name, akvc_macos_resolved_shm_name(), sizeof(out_desc->shm_name) - 1);
}

uint32_t akvc_macos_default_region_size(void) {
    return AKVC_DEFAULT_REGION_SIZE;
}
