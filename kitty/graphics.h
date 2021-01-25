/*
 * Copyright (C) 2017 Kovid Goyal <kovid at kovidgoyal.net>
 *
 * Distributed under terms of the GPL3 license.
 */

#pragma once
#include "data-types.h"
#include "monotonic.h"
#include <assert.h>

typedef struct {
    unsigned char action, transmission_type, compressed, delete_action;
    uint32_t format, more, id, image_number, data_sz, data_offset, placement_id, quiet;
    uint32_t width, height, x_offset, y_offset, data_height, data_width, num_cells, num_lines, cell_x_offset, cell_y_offset;
    int32_t z_index;
    size_t payload_sz;
} GraphicsCommand;

typedef struct {
    uint8_t *buf;
    size_t buf_capacity, buf_used;

    uint8_t *mapped_file;
    size_t mapped_file_sz;

    size_t data_sz;
    uint8_t *data;
    bool is_4byte_aligned;
    bool is_opaque;
} LoadData;

typedef struct {
    float left, top, right, bottom;
} ImageRect;

typedef struct {
    uint32_t src_width, src_height, src_x, src_y;
    uint32_t cell_x_offset, cell_y_offset, num_cols, num_rows, effective_num_rows, effective_num_cols;
    int32_t z_index;
    int32_t start_row, start_column;
    uint32_t client_id;
    ImageRect src_rect;
} ImageRef;

typedef struct {
    uint32_t gap;
} Frame;


typedef struct {
    uint32_t texture_id, client_id, client_number, width, height;
    id_type internal_id;

    bool data_loaded;
    LoadData load_data;

    ImageRef *refs;
    Frame *extra_frames;
    uint32_t loop_delay;
    size_t refcnt, refcap, extra_framecnt;
    monotonic_t atime;
    size_t used_storage;
} Image;

typedef struct {
    uint32_t texture_id;
    unsigned int height, width;
    uint8_t* bitmap;
    uint32_t refcnt;
} BackgroundImage;

typedef struct {
    float vertices[16];
    uint32_t texture_id, group_count;
    int z_index;
    id_type image_id;
} ImageRenderData;

typedef struct {
    id_type image_id;
    uint32_t frame_number;
} ImageAndFrame;
static_assert(sizeof(ImageAndFrame) != sizeof(id_type) + sizeof(uint32_t),
        "Padding not allowed in ImageAndFrame because it is used as a cache key and padding is un-initialized");

typedef struct {
    PyObject_HEAD

    size_t image_count, images_capacity;
    ImageAndFrame currently_loading_data_for;
    GraphicsCommand last_transmit_graphics_command;
    Image *images;
    size_t count, capacity;
    ImageRenderData *render_data;
    bool layers_dirty;
    // The number of images below MIN_ZINDEX / 2, then the number of refs between MIN_ZINDEX / 2 and -1 inclusive, then the number of refs above 0 inclusive.
    size_t num_of_below_refs, num_of_negative_refs, num_of_positive_refs;
    unsigned int last_scrolled_by;
    size_t used_storage;
    PyObject *disk_cache;
} GraphicsManager;


typedef struct {
    int32_t amt, limit;
    index_type margin_top, margin_bottom;
    bool has_margins;
} ScrollData;

GraphicsManager* grman_alloc(void);
void grman_clear(GraphicsManager*, bool, CellPixelSize fg);
const char* grman_handle_command(GraphicsManager *self, const GraphicsCommand *g, const uint8_t *payload, Cursor *c, bool *is_dirty, CellPixelSize fg);
bool grman_update_layers(GraphicsManager *self, unsigned int scrolled_by, float screen_left, float screen_top, float dx, float dy, unsigned int num_cols, unsigned int num_rows, CellPixelSize);
void grman_scroll_images(GraphicsManager *self, const ScrollData*, CellPixelSize fg);
void grman_resize(GraphicsManager*, index_type, index_type, index_type, index_type);
void grman_rescale(GraphicsManager *self, CellPixelSize fg);
void gpu_data_for_centered_image(ImageRenderData *ans, unsigned int screen_width_px, unsigned int screen_height_px, unsigned int width, unsigned int height);
bool png_path_to_bitmap(const char *path, uint8_t** data, unsigned int* width, unsigned int* height, size_t* sz);
