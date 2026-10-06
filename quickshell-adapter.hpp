#pragma once

// Optional adapter linked against reviewed Quickshell static modules. No shell
// executable, IPC server, compositor connection or production config is started.
#include <QDir>
#include <QQmlEngine>
#include <qqml.h>
#include "core/generation.hpp"
#include "core/plugin.hpp"
#include "core/scan.hpp"
#include "wayland/wlr_layershell/wlr_layershell.hpp"

inline void initializeQuickshellPreview() {
    qunsetenv("WAYLAND_DISPLAY");
    qunsetenv("HYPRLAND_INSTANCE_SIGNATURE");
    QsEnginePlugin::initPlugins();
    // The real layer-shell interface is made loadable on offscreen QPA. Its
    // compositor bridge is absent: only the actual content subtree is captured.
    qmlRegisterType<qs::wayland::layershell::WaylandPanelInterface>(
        "Quickshell._PreviewOverlay", 1, 0, "PanelWindow");
    qmlRegisterModuleImport("Quickshell", QQmlModuleImportModuleAny,
                           "Quickshell._PreviewOverlay", QQmlModuleImportLatest);
}

inline EngineGeneration *createQuickshellPreview(const QString &path, const QJsonArray &imports) {
    QDir root(QFileInfo(path).absolutePath());
    for (const auto &value : imports) {
        QDir candidate(value.toString());
        if (QFileInfo(candidate.filePath("shell.qml")).isFile()
            && QFileInfo(candidate.filePath("Commons/qmldir")).isFile()) {
            root = candidate;
            break;
        }
    }
    return new EngineGeneration(root, QmlScanner(root));
}
