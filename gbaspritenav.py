#!/usr/bin/env python3
# -*- coding: utf8 -*-
# 
# gbaspritenav - Sprite navigator for GBA hackers
# Currently works with Pokemon Fire Red, yet to be tested with other games.
# 
# Copyright (C) 2015 euhmeuh
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import struct
from gi.repository import Gtk
from gi.repository.GdkPixbuf import Pixbuf, InterpType, Colorspace

## consts

# one pixel is 4 bits
# 4 bytes makes 8 pixels
# a block is 8 rows of 8 pixels
# a block is 8 rows of 4 bytes
# a block is 24 bytes
ROW = 4
BLOCK = ROW * 8

## tools
def cut(iterable, chunksize):
    return [iterable[i:i+chunksize] for i in range(0, len(iterable), chunksize)]

def get_selected(iconview, liststore):
    result = []
    for path in iconview.get_selected_items():
        iterable = liststore.get_iter(path)
        obj = []
        for col in range(liststore.get_n_columns()):
            obj.append(liststore.get_value(iterable, col))
        result.append(obj)
    return result

## objects
class ROM:
    def __init__(self, filename):
        self.filename = filename

    def search(self, offset, size, paloffset, qty):
        sprites = []
        try:
            with open(self.filename, 'rb') as f:
                # read palette
                f.seek(paloffset)
                palette = Palette(f.read(32), paloffset)

                # read sprites
                f.seek(offset)
                length = size[0] * size[1] * BLOCK
                for os in range(offset, offset + qty*length, length):
                    sprite = Sprite(f.read(length), os, size, palette)
                    sprites.append(sprite)
        except FileNotFoundError as e:
            print(e)
            pass
        return sprites


class Sprite:
    def __init__(self, data, offset, size, palette):
        self.name = ""
        self.offset = offset
        self.size = size
        self.length = self.size[0] * self.size[1] * BLOCK
        self.palette = palette
        self.image = Image(data, size, palette)


# An image is made of blocks
# A block has 8 rows of pixels
# A row of pixel is 4 bytes and represents 8 pixels
# A byte has two pixels in reverse order : BBBBAAAA
class Image:
    def __init__(self, data, size, palette):
        if not data:
            # dummy image
            self.pixbuf = Pixbuf.new(Colorspace.RGB, False, 8,
                                     size[0] * 8 * 2, size[1] * 8 * 2)
            self.pixbuf.fill(0xAAAAAAFF)
            return

        # slice into blocks
        blocks = cut(data, BLOCK)
        # slice block content
        blocks = [cut(b, ROW) for b in blocks]
        # rearrange into blockrows (y/x coordinates)
        blocks = cut(blocks, size[0])

        bytestring = []
        # for each block row
        for y in range(0, size[1]):
            # for each final row
            for i in range(0, int(BLOCK / ROW)):
                # for each block column
                for x in range(0, size[0]):
                    r = blocks[y][x][i]
                    # extract pixels from rows
                    for j in range(4):
                        bytestring.append(r[j] & 0x0F)  # first  (....AAAA)
                        bytestring.append(r[j] >> 4)    # second (BBBB....)

        # apply palette
        result = []
        for i in bytestring:
            result += palette.colors[i]

        # get result in binary format
        result = b''+bytearray(result)

        # create image
        self.pixbuf = Pixbuf.new_from_data(
            result, 0, False, 8,
            8 * size[0], 8 * size[1], 8 * size[0] * 3, None, None)
        self.pixbuf = self.pixbuf.scale_simple(
            8 * size[0] * 2, 8 * size[1] * 2, InterpType.NEAREST)


# A palette is 32 bytes
# It contains 16 colors (2 bytes each)
# Each color is 15bits (R5 G5 B5)
# Colors are in reverse order : 0BBBBBGGGGGRRRRR
class Palette:
    def __init__(self, data, offset):
        self.offset = offset

        if not data:
            self.colors = []
            return

        colors = [int(struct.unpack('H', c[0:2])[0]) for c in cut(data, 2)]
        self.colors = [[
            (c & 0x001F) * 8,         # R
            ((c & 0x03E0) >> 5) * 8,  # G
            ((c & 0x7C00) >> 10) * 8  # B
        ] for c in colors]


## --- app context ---

class SearchForm:
    def __init__(self):
        self.offset = 0x000000
        self.palette = 0x000000
        self.size = (1, 1)
        self.qty = 1

        #                              image, name, offset
        self.iconstore = Gtk.ListStore(Pixbuf, str, int)
        self.sprites = []

    def search(self):
        self.iconstore.clear()
        self.sprites = Context.rom.search(self.offset, self.size, self.palette, self.qty)
        for sprite in self.sprites:
            # check if sprite result is in bookmarks
            name = Context.bookmarks_form.get_name(sprite)
            if name:
                text = name + '\n' + hex(sprite.offset)
            else:
                text = hex(sprite.offset)
            self.iconstore.append([sprite.image.pixbuf, text, sprite.offset])

class BookmarksForm:
    def __init__(self):
        self.iconstore = Gtk.ListStore(Pixbuf, str, int)
        self.iconstore.set_default_sort_func(BookmarksForm.sort, self)
        self.iconstore.set_sort_column_id(Gtk.TREE_SORTABLE_DEFAULT_SORT_COLUMN_ID, Gtk.SortType.ASCENDING)
        self.sprites = []

    def load(self, bookmarks):
        self.sprites = []
        self.iconstore.clear()
        for offset, bkm in bookmarks.items():
            sprite = None
            try:
                sprite = Context.rom.search(offset, bkm[2], bkm[1], 1)[0]
            except IndexError:
                # the sprite was not found, put dummy data
                sprite = Sprite("", offset, bkm[2], Palette("", bkm[1]))

            # add sprite to the list
            sprite.name = bkm[0]
            self.sprites.append(sprite)
            # refresh iconview
            self.iconstore.append([sprite.image.pixbuf,
                sprite.name + '\n' + hex(sprite.offset), sprite.offset])


    def get_name(self, sprite):
        for s in self.sprites:
            if(sprite.offset == s.offset
            and sprite.size == s.size):
                return s.name
        return ""

    def get_sprite(self, offset):
        for sprite in self.sprites:
            if sprite.offset == offset:
                return sprite
        return None

    @classmethod
    def sort(cls, model, a, b, user_data):
        value1 = user_data.get_sprite(model.get_value(a, 2))
        value2 = user_data.get_sprite(model.get_value(b, 2))
        if value1.length < value2.length:
            return -1
        elif value1.length == value2.length:
            return -1 if (value1.offset < value2.offset) else 1
        else:
            return 1

class Context:
    rom = None
    search_form = SearchForm()
    bookmarks_form = BookmarksForm()


## --- interface code ---

class Interface:
    def __init__(self):
        # main window
        self.builder = Gtk.Builder.new_from_file('gbaspritenav.glade')
        self.win = self.builder.get_object("window_main")

        # get interesting objects
        searchview = self.builder.get_object("iconview_search")
        searchview.set_model(Context.search_form.iconstore)
        searchview.set_pixbuf_column(0)
        text_renderer = Gtk.CellRendererText()  # fixes wrong width calculation
        searchview.pack_end(text_renderer, False)
        searchview.add_attribute(text_renderer, 'text', 1)

        bookmarksview = self.builder.get_object("iconview_bookmarks")
        bookmarksview.set_model(Context.bookmarks_form.iconstore)
        bookmarksview.set_pixbuf_column(0)
        text_renderer = Gtk.CellRendererText()  # fixes wrong width calculation
        bookmarksview.pack_end(text_renderer, False)
        bookmarksview.add_attribute(text_renderer, 'text', 1)

        spin_search_offset = self.builder.get_object("spinbutton_search_offset")
        spin_search_palette = self.builder.get_object("spinbutton_search_palette")
        button_search = self.builder.get_object("button_search")

        # connect events
        self.win.connect("delete-event", Gtk.main_quit)
        spin_search_offset.connect("value-changed", self.on_spinbutton_offset_changed)
        spin_search_offset.connect("output", self.on_spinbutton_output)
        spin_search_palette.connect("value-changed", self.on_spinbutton_palette_changed)
        spin_search_palette.connect("output", self.on_spinbutton_output)
        bookmarksview.connect("selection-changed", self.on_bookmarks_selection)
        button_search.connect("clicked", self.on_search)

    def show(self):
        # show all
        self.win.show_all()
        Gtk.main()

    def on_spinbutton_offset_changed(self, spin_button):
        try:
            Context.search_form.offset = int(spin_button.get_text(), 16)
        except ValueError:
            Context.search_form.offset = 0
        else:
            self.on_search(spin_button)

    def on_spinbutton_palette_changed(self, spin_button):
        try:
            Context.search_form.palette = int(spin_button.get_text(), 16)
        except ValueError:
            Context.search_form.palette = 0
        else:
            self.on_search(spin_button)

    def on_spinbutton_output(self, spin_button):
        value = int(spin_button.get_adjustment().get_value())
        spin_button.set_text(hex(value))
        return True

    def on_bookmarks_selection(self, iconview):
        # get all the entries
        name = self.builder.get_object("entry_details_name")
        offset = self.builder.get_object("entry_details_offset")
        palette = self.builder.get_object("entry_details_palette")
        width = self.builder.get_object("entry_details_width")
        height = self.builder.get_object("entry_details_height")
        image = self.builder.get_object("image_selected")

        sprite_id = None
        # update entries
        try:
            selected = get_selected(iconview, Context.bookmarks_form.iconstore)[0]
            sprite_id = selected[2]
        except IndexError:
            # no selection
            name.set_text("")
            offset.set_text("")
            palette.set_text("")
            width.set_text("")
            height.set_text("")
            image.set_from_stock("gtk-missing-image", Gtk.IconSize.BUTTON)
        else:
            # we have a selection
            sprite = Context.bookmarks_form.get_sprite(sprite_id)
            name.set_text(sprite.name)
            offset.set_text(hex(sprite.offset))
            palette.set_text(hex(sprite.palette.offset))
            width.set_text(str(sprite.size[0]))
            height.set_text(str(sprite.size[1]))
            pix = sprite.image.pixbuf
            image.set_from_pixbuf(
                pix.scale_simple(min(128, pix.get_width()),
                                 min(128, pix.get_height()), InterpType.NEAREST))


    def on_search(self, button):
        width = self.builder.get_object("entry_search_width")
        height = self.builder.get_object("entry_search_height")
        qty = self.builder.get_object("spinbutton_search_qty")
        try:
            Context.search_form.size = (int(width.get_text()), int(height.get_text()))
            Context.search_form.qty = int(qty.get_value())
        except ValueError:
            Context.search_form.size = (1, 1)
            Context.search_form.qty = 1
        Context.search_form.search()


if __name__ == '__main__':
    Context.rom = ROM("../Moekarp/Moekarp Fire Red.gba")
    bookmarks = {
        0x35D268: ["OW Girl Front", 0x35B968, (2, 4)],
        0x363DA8: ["OW Girl Bike Front", 0x35B968, (4, 4)],
        0xeaea80: ["Gameboy tileset", 0xeaea40, (16, 10)],
        0xe95ddc: ["Types", 0xe95dbc, (16, 16)],
        0x3c2d40: ["Fog1", 0x3c2ce0, (8, 8)],
        0x3c3540: ["Fog2", 0x3c2ce0, (8, 8)],
        0x3c3d40: ["Clouds", 0x3c2d00, (8, 8)],
        0x3c6ac8: ["Exclamations", 0x35b968, (2, 30)],
        0x360da8: ["On Lapras' Back", 0x35b988, (4, 4)],
        0x39d3c8: ["Let's fly away! 00", 0x35b988, (8, 8)],
        0x39dbc8: ["Let's fly away! 01", 0x35b988, (8, 8)],
        0x39e3c8: ["Let's fly away! 02", 0x35b988, (8, 8)],
        0x39ebc8: ["Let's fly away! 03", 0x35b988, (8, 8)],
        0x39f3c8: ["Let's fly away! 04", 0x35b988, (8, 8)]
    }
    Context.bookmarks_form.load(bookmarks)
    Interface().show()
