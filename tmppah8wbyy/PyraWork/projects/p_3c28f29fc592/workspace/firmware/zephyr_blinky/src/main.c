#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

#define LED0_NODE DT_ALIAS(led0)

#if !DT_NODE_EXISTS(LED0_NODE)
#error "No led0 alias in board DTS — cannot build blinky for this board"
#endif

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

int main(void)
{
        if (!gpio_is_ready_dt(&led)) {
                return 0;
        }
        gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
        while (1) {
                gpio_pin_toggle_dt(&led);
                k_msleep(500);
        }
        return 0;
}
