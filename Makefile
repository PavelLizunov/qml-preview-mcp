CXX ?= c++
CXXFLAGS ?= -O2 -Wall -Wextra -Wpedantic
QT_CFLAGS := $(shell pkg-config --cflags Qt6Quick)
QT_LIBS := $(shell pkg-config --libs Qt6Quick)

.PHONY: all check clean
all: qml-render

qml-render: qml-render.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -fPIC -std=c++17 $(QT_CFLAGS) $< -o $@ $(LDFLAGS) $(QT_LIBS)

check: qml-render
	PYTHONDONTWRITEBYTECODE=1 python3 tests/smoke.py

clean:
	rm -f qml-render
