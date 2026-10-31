#include "cam.h"
#include "data.h"

#define BAND_H 44
#define PALETTE_SIZE 16

static Window *s_window;
static Layer *s_canvas;
static GBitmap *s_bitmap;
static char s_name[NAME_BYTES + 1];
static int s_index;
static int s_len;            // bytes of pixel data announced by the phone
static int s_received;
static int s_stride;         // bytes per row as sent: ceil(width / 2)
static time_t s_taken;       // the image's Last-Modified time, 0 = unknown
static char s_error[32];

static void text(GContext *ctx, const char *s, const char *font_key, GRect box, GTextAlignment align) {
  graphics_draw_text(ctx, s, fonts_get_system_font(font_key), box,
                     GTextOverflowModeTrailingEllipsis, align, NULL);
}

static void reset(void) {
  if (s_bitmap) {
    gbitmap_destroy(s_bitmap);
    s_bitmap = NULL;
  }
  s_len = 0;
  s_received = 0;
  s_taken = 0;
  s_error[0] = '\0';
}

static void request(void) {
  reset();
  DictionaryIterator *out;
  if (app_message_outbox_begin(&out) == APP_MSG_OK) {
    dict_write_int32(out, MESSAGE_KEY_CAM_REQ, s_index);
    app_message_outbox_send();
  } else {
    snprintf(s_error, sizeof(s_error), "phone busy, press Select");
  }
  if (s_canvas) {
    layer_mark_dirty(s_canvas);
  }
}

static void status(char *buf, size_t size) {
  if (s_error[0]) {
    snprintf(buf, size, "%s", s_error);
  } else if (!s_bitmap || s_received < s_len) {
    snprintf(buf, size, "Loading webcam...");
  } else if (s_taken) {
    int mins = (time(NULL) - s_taken) / 60;
    if (mins < 60) {
      snprintf(buf, size, "image %d min old", mins < 0 ? 0 : mins);
    } else {
      snprintf(buf, size, "image %d h old", mins / 60);
    }
  } else {
    snprintf(buf, size, "webcam");
  }
}

static void draw(Layer *layer, GContext *ctx) {
  GRect b = layer_get_bounds(layer);
  int w = b.size.w;
  char line[40];

  graphics_context_set_fill_color(ctx, GColorOxfordBlue);
  graphics_fill_rect(ctx, GRect(0, 0, w, BAND_H), 0, GCornerNone);
  graphics_context_set_text_color(ctx, GColorWhite);
  text(ctx, s_name, FONT_KEY_GOTHIC_24_BOLD, GRect(6, -4, w - 12, 28), GTextAlignmentLeft);
  status(line, sizeof(line));
  graphics_context_set_text_color(ctx, s_error[0] ? GColorMelon : GColorCeleste);
  text(ctx, line, FONT_KEY_GOTHIC_18, GRect(6, 20, w - 12, 22), GTextAlignmentLeft);

  int img_h = 0;
  if (s_bitmap) {
    GSize size = gbitmap_get_bounds(s_bitmap).size;
    img_h = size.h;
    graphics_context_set_compositing_mode(ctx, GCompOpAssign);
    graphics_draw_bitmap_in_rect(ctx, s_bitmap, GRect((w - size.w) / 2, BAND_H, size.w, size.h));
  }
  int y = BAND_H + (img_h ? img_h : 120) + 8;
  if (!s_error[0] && s_received < s_len) {
    graphics_context_set_stroke_color(ctx, GColorLightGray);
    graphics_draw_rect(ctx, GRect(20, y, w - 40, 8));
    graphics_context_set_fill_color(ctx, GColorVividCerulean);
    graphics_fill_rect(ctx, GRect(21, y + 1, (w - 42) * s_received / s_len, 6), 0, GCornerNone);
  }
  graphics_context_set_text_color(ctx, GColorDarkGray);
  text(ctx, "Select: reload", FONT_KEY_GOTHIC_18, GRect(6, b.size.h - 26, w - 12, 22), GTextAlignmentCenter);
}

bool cam_handle_message(DictionaryIterator *iter) {
  Tuple *width = dict_find(iter, MESSAGE_KEY_CAM_W);
  Tuple *data = dict_find(iter, MESSAGE_KEY_CAM_DATA);
  Tuple *error = dict_find(iter, MESSAGE_KEY_CAM_ERR);
  if (!width && !data && !error) {
    return false;
  }
  if (!s_canvas) {
    return true;  // the webcam screen was closed; drop late chunks
  }
  if (error) {
    snprintf(s_error, sizeof(s_error), "%s", error->value->cstring);
  }
  if (width) {
    Tuple *height = dict_find(iter, MESSAGE_KEY_CAM_H);
    Tuple *pal = dict_find(iter, MESSAGE_KEY_CAM_PAL);
    Tuple *len = dict_find(iter, MESSAGE_KEY_CAM_LEN);
    Tuple *taken = dict_find(iter, MESSAGE_KEY_CAM_TIME);
    if (height && pal && len && pal->length == PALETTE_SIZE) {
      reset();
      GColor *palette = malloc(PALETTE_SIZE * sizeof(GColor));
      if (palette) {
        memcpy(palette, pal->value->data, PALETTE_SIZE);  // GColor8: one ARGB byte each
        s_bitmap = gbitmap_create_blank_with_palette(GSize(width->value->int32, height->value->int32),
                                                     GBitmapFormat4BitPalette, palette, true);
      }
      if (!s_bitmap) {
        free(palette);
        snprintf(s_error, sizeof(s_error), "out of memory");
      }
      s_stride = (width->value->int32 + 1) / 2;
      s_len = len->value->int32;
      s_taken = taken ? taken->value->int32 : 0;
    }
  }
  if (data && s_bitmap) {
    Tuple *off = dict_find(iter, MESSAGE_KEY_CAM_OFF);
    int offset = off ? off->value->int32 : 0;
    uint8_t *pixels = gbitmap_get_data(s_bitmap);
    int bytes_per_row = gbitmap_get_bytes_per_row(s_bitmap);
    for (int i = 0; i < data->length && offset + i < s_len; i++) {
      int o = offset + i;
      pixels[(o / s_stride) * bytes_per_row + o % s_stride] = data->value->data[i];
    }
    s_received = offset + data->length;
  }
  layer_mark_dirty(s_canvas);
  return true;
}

static void select_click(ClickRecognizerRef rec, void *ctx) {
  request();
}

static void click_config(void *ctx) {
  window_single_click_subscribe(BUTTON_ID_SELECT, select_click);
}

static void window_load(Window *window) {
  Layer *root = window_get_root_layer(window);
  s_canvas = layer_create(layer_get_bounds(root));
  layer_set_update_proc(s_canvas, draw);
  layer_add_child(root, s_canvas);
}

static void window_unload(Window *window) {
  layer_destroy(s_canvas);
  s_canvas = NULL;
  reset();
}

void cam_push(int index, const char *name) {
  if (!s_window) {
    s_window = window_create();
    window_set_background_color(s_window, GColorWhite);
    window_set_click_config_provider(s_window, click_config);
    window_set_window_handlers(s_window, (WindowHandlers) {
      .load = window_load,
      .unload = window_unload,
    });
  }
  s_index = index;
  snprintf(s_name, sizeof(s_name), "%s", name);
  window_stack_push(s_window, true);
  request();
}

void cam_deinit(void) {
  if (s_window) {
    window_destroy(s_window);
  }
}
