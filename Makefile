CXX ?= c++
CXXFLAGS ?= -O2 -Wall -Wextra -Wpedantic
ifeq ($(shell pkg-config --exists Qt6Quick && printf yes),yes)
QT_CFLAGS := $(shell pkg-config --cflags Qt6Quick)
QT_LIBS := $(shell pkg-config --libs Qt6Quick)
else
# Ubuntu 22.04's Qt 6 packages omit .pc files; query the installed Qt paths.
QT_HEADERS := $(shell qmake6 -query QT_INSTALL_HEADERS)
QT_LIBRARY_DIR := $(shell qmake6 -query QT_INSTALL_LIBS)
QT_CFLAGS := -I$(QT_HEADERS) $(foreach module,Core Gui Qml Quick,-I$(QT_HEADERS)/Qt$(module))
QT_LIBS := -L$(QT_LIBRARY_DIR) -lQt6Quick -lQt6Qml -lQt6Gui -lQt6Core
endif

.PHONY: all check clean
all: qml-render

qml-render: qml-render.cpp Makefile
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -fPIC -std=c++17 $(QT_CFLAGS) $< -o $@ $(LDFLAGS) $(QT_LIBS)

check: qml-render
	PYTHONDONTWRITEBYTECODE=1 python3 tests/smoke.py
	PYTHONDONTWRITEBYTECODE=1 python3 tests/v03.py

clean:
	rm -f qml-render
