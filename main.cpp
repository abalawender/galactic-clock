//#include <stdio.h>
//#include <stdlib.h>
#include <sstream>
#include <iomanip>
#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"

#include "libraries/pico_graphics/pico_graphics.hpp"
#include "libraries/galactic_unicorn/galactic_unicorn.hpp"
#include "okcolor.hpp"
#include "wifi_credentials.hpp"
#include "libraries/bitmap_fonts/font6_data.hpp"

#include "pico/bootrom.h"

extern "C" {
#include "ntp.h"
}

// could also use https://worldtimeapi.org/api/ for time

using namespace pimoroni;

PicoGraphics_PenRGB888 graphics(GalacticUnicorn::WIDTH, GalacticUnicorn::HEIGHT, nullptr);
GalacticUnicorn galactic_unicorn;


int setup_wifi() {

    if (cyw43_arch_init_with_country(CYW43_COUNTRY_SWITZERLAND))
    {
        printf("failed to initialise\n");
        return 1;
    }
    printf("initialised\n");

    cyw43_arch_enable_sta_mode();

    return cyw43_arch_wifi_connect_async(WifiCredentials::ssid, WifiCredentials::pass, CYW43_AUTH_WPA2_AES_PSK);
}

int wifi_state() {
    // CYW43_LINK_DOWN         (0)     ///< link is down
    // CYW43_LINK_JOIN         (1)     ///< Connected to wifi
    // CYW43_LINK_NOIP         (2)     ///< Connected to wifi, but no IP address
    // CYW43_LINK_UP           (3)     ///< Connect to wifi with an IP address
    // CYW43_LINK_FAIL         (-1)    ///< Connection failed
    // CYW43_LINK_NONET        (-2)    ///< No matching SSID found (could be out of range, or down)
    // CYW43_LINK_BADAUTH      (-3)    ///< Authenticatation failure
    return cyw43_tcpip_link_status(&cyw43_state, CYW43_ITF_STA);
}

int main() {

    stdio_init_all();

    galactic_unicorn.init();
    graphics.set_font(&font6);

    setup_wifi();

    int flip = 1;

    float brightness_offset = 0.0;

    while(true) {

        if(galactic_unicorn.is_pressed(galactic_unicorn.SWITCH_BRIGHTNESS_UP)) {
            brightness_offset += 0.01;
        }
        else if(galactic_unicorn.is_pressed(galactic_unicorn.SWITCH_BRIGHTNESS_DOWN)) {
            brightness_offset -= 0.01;
        }
        else if(galactic_unicorn.is_pressed(galactic_unicorn.SWITCH_SLEEP)) {
            reset_usb_boot(0, 0);
        }

        galactic_unicorn.set_brightness(galactic_unicorn.light()/400.0f + brightness_offset);

        graphics.set_pen(0, 0, 0);
        graphics.clear();

        graphics.set_pen(255*flip, 0, 0);
        flip ^= 1;
        graphics.pixel(Point(0, 0));


        int ntpstate = 1;
        if (wifi_state() == 3) {
            ntpstate = setup_ntp();
        }

        std::stringstream ss;
        //ss << "L: " << galactic_unicorn.light()/10;
        //ss << wifi_state() << ntpstate << " ";

        struct tm *utc = gmtime(&ntp_time);
        ss << std::setw(2) << utc->tm_hour << ":" << std::setfill('0') << std::setw(2) << utc->tm_min << ":" << std::setw(2) << utc->tm_sec;

        graphics.set_pen(127, 255, 64);
        graphics.text(ss.str(), Point(0, 1), GalacticUnicorn::WIDTH, 1);

        // now we've done our drawing let's update the screen
        galactic_unicorn.update(&graphics);

        sleep_ms(100);
        run_ntp();
        
    }

    cyw43_arch_deinit();
}