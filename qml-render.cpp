#include <QFile>
#include <QFileInfo>
#include <QFont>
#include <QDateTime>
#include <QLocale>
#include <QGuiApplication>
#include <QImageReader>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaProperty>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQuickView>
#include <QMutex>
#include <QMutexLocker>
#include <QTimer>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <functional>

#ifdef QML_PREVIEW_QUICKSHELL
#include "quickshell-adapter.hpp"
#endif

static constexpr auto version = "0.3.0";
static constexpr int metadataLimit = 512 * 1024;

static void platform(int dpr) {
    qunsetenv("QML_IMPORT_PATH");
    qunsetenv("QML2_IMPORT_PATH");
    qunsetenv("QT_SCREEN_SCALE_FACTORS");
    qputenv("QT_QPA_PLATFORM", "offscreen");
    qputenv("QT_QUICK_BACKEND", "software");
    qputenv("QSG_RENDER_LOOP", "basic");
    qputenv("QT_SCALE_FACTOR", QByteArray::number(dpr));
    qputenv("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough");
    qputenv("QT_FONT_DPI", "96");
}

static void jsonOutput(const QJsonObject &object) {
    const QByteArray json = QJsonDocument(object).toJson(QJsonDocument::Compact) + '\n';
    std::fwrite(json.constData(), 1, json.size(), stdout);
    std::fflush(stdout);
}

static void boundedLog(QtMsgType type, const QMessageLogContext &context, const QString &message) {
    static QMutex mutex;
    QMutexLocker lock(&mutex);
    static int remaining = 65536;
    const char *level = type == QtDebugMsg ? "debug" : type == QtInfoMsg ? "info"
        : type == QtWarningMsg ? "warning" : type == QtCriticalMsg ? "critical" : "fatal";
    const QJsonObject record {{"level", level}, {"message", message.left(4096)},
        {"source", context.file ? QJsonValue(QString::fromUtf8(context.file).left(1024)) : QJsonValue(QJsonValue::Null)},
        {"line", context.line}, {"category", context.category ? QString::fromUtf8(context.category).left(128) : "qt"}};
    const QByteArray bytes = QJsonDocument(record).toJson(QJsonDocument::Compact) + '\n';
    const QByteArray dropped = "{\"level\":\"warning\",\"message\":\"Diagnostics truncated\",\"category\":\"limit\"}\n";
    if (remaining >= bytes.size() + dropped.size()) {
        std::fwrite(bytes.constData(), 1, bytes.size(), stderr);
        remaining -= bytes.size();
    } else if (remaining >= dropped.size()) {
        std::fwrite(dropped.constData(), 1, dropped.size(), stderr);
        remaining = 0;
    }
    if (type == QtFatalMsg)
        std::abort();
}

static QJsonObject geometry(QQuickItem *item) {
    const QRectF bounds = item->mapRectToScene(QRectF(0, 0, item->width(), item->height()));
    const QList<double> numbers {bounds.x(), bounds.y(), bounds.width(), bounds.height(),
                                item->implicitWidth(), item->implicitHeight()};
    for (double number : numbers) {
        if (!std::isfinite(number))
            return {};
    }
    return {{"x", bounds.x()}, {"y", bounds.y()}, {"width", bounds.width()}, {"height", bounds.height()},
            {"implicitWidth", item->implicitWidth()}, {"implicitHeight", item->implicitHeight()},
            {"visible", item->isVisible()}, {"enabled", item->isEnabled()}, {"clip", item->clip()},
            {"activeFocus", item->hasActiveFocus()}, {"coordinateSpace", "logical-scene-axis-aligned"}};
}

// Traverse visual ownership, not QObject parentage; bounded admission prevents
// snapshots or name lookup from expanding without a finite work budget.
static bool visualItems(QQuickItem *root, QList<QQuickItem *> &items) {
    items.append(root);
    for (int i = 0; i < items.size(); ++i) {
        const auto children = items[i]->childItems();
        if (items.size() + children.size() > 10000)
            return false;
        items.append(children);
    }
    return true;
}

static QJsonObject snapshot(QQuickItem *root, const QJsonObject &options) {
    const int maxDepth = options.value("maxDepth").toInt(6);
    const int maxItems = options.value("maxItems").toInt(64);
    QJsonArray nodes;
    struct Entry { QQuickItem *item; int depth; int parent; };
    QList<Entry> pending {{root, 0, -1}};
    bool truncated = false;
    while (!pending.isEmpty() && nodes.size() < maxItems) {
        const Entry entry = pending.takeLast();
        auto node = geometry(entry.item);
        node.insert("geometryValid", !node.isEmpty());
        node.insert("index", nodes.size());
        node.insert("parent", entry.parent < 0 ? QJsonValue(QJsonValue::Null) : QJsonValue(entry.parent));
        node.insert("depth", entry.depth);
        node.insert("type", QString::fromUtf8(entry.item->metaObject()->className()).left(128));
        node.insert("objectName", entry.item->objectName().left(128));
        const QVariant text = entry.item->property("text");
        if (text.metaType().id() == QMetaType::QString) {
            node.insert("text", text.toString().left(256));
            node.insert("textTruncated", text.toString().size() > 256);
        }
        const int parentIndex = nodes.size();
        nodes.append(node);
        const auto children = entry.item->childItems();
        if (entry.depth >= maxDepth) {
            truncated = truncated || !children.isEmpty();
            continue;
        }
        // Add only nodes that could fit; report omitted siblings explicitly.
        const int budget = maxItems - nodes.size() - pending.size();
        const int count = qMax(0, qMin(budget, int(children.size())));
        truncated = truncated || count < children.size();
        for (int i = count - 1; i >= 0; --i)
            pending.append({children[i], entry.depth + 1, parentIndex});
    }
    return {{"nodes", nodes}, {"truncated", truncated || !pending.isEmpty()},
            {"maxItems", maxItems}, {"maxDepth", maxDepth}, {"kind", "QQuickItem-visual-tree"},
            {"accessibilityVerified", false}};
}

static bool integer(const QJsonValue &value, int low, int high) {
    const double number = value.toDouble(-1);
    return value.isDouble() && std::isfinite(number) && number == std::floor(number)
           && number >= low && number <= high;
}

int main(int argc, char **argv) {
    if (argc == 2 && QByteArray(argv[1]) == "--healthcheck") {
        platform(1);
        qInstallMessageHandler(boundedLog);
        int qtArgc = 1;
        QGuiApplication app(qtArgc, argv);
        QQmlEngine engine;
        auto paths = engine.importPathList();
#ifdef QML_PREVIEW_QUICKSHELL
        const bool quickshellModules = true;
#else
        const bool quickshellModules = false;
#endif
        paths.removeAll(QCoreApplication::applicationDirPath());
        jsonOutput({{"rendererVersion", version}, {"qtVersion", qVersion()},
                    {"platform", QGuiApplication::platformName()}, {"backend", "software"},
                    {"qtImportPaths", QJsonArray::fromStringList(paths)},
                    {"rootTypes", QJsonArray {"QQuickItem", "Item", "Rectangle"}},
                    {"supportedDpr", QJsonArray {1, 2}}, {"interaction", false},
                    {"qmlExecuted", false}, {"shaderEffects", false},
                    {"quickshellModules", quickshellModules}});
        return 0;
    }
    if (argc != 3 || QByteArray(argv[1]) != "--output-fd") {
        std::fprintf(stderr, "Usage: qml-render --output-fd <inherited writable fd>; JSON request on stdin\n");
        return 1;
    }
    bool fdValid = false;
    const int outputFd = QByteArray(argv[2]).toInt(&fdValid);
    if (!fdValid || outputFd < 3)
        return 1;
    QFile input;
    if (!input.open(stdin, QIODevice::ReadOnly)) {
        std::fprintf(stderr, "Cannot read renderer stdin\n");
        return 1;
    }
    const QByteArray request = input.read(1024 * 1024 + 1);
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(request, &parseError);
    if (request.size() > 1024 * 1024 || parseError.error != QJsonParseError::NoError || !document.isObject()) {
        std::fprintf(stderr, "Invalid renderer JSON request\n");
        return 1;
    }
    const QJsonObject config = document.object();
    if (config.value("expectedVersion").toString() != version) {
        std::fprintf(stderr, "Renderer/wrapper version mismatch\n");
        return 1;
    }
    const QString qmlPath = config.value("qmlPath").toString();
    const QString readyName = config.value("readyProperty").toString();
    if (!QFileInfo(qmlPath).isAbsolute() || !QFileInfo(qmlPath).isFile()
        || !integer(config.value("width"), 1, 4096) || !integer(config.value("height"), 1, 4096)
        || !integer(config.value("dpr"), 1, 2) || !integer(config.value("timeoutMs"), 100, 10000)
        || !config.value("importPaths").isArray() || config.value("importPaths").toArray().size() > 32
        || (config.contains("initialProperties") && (!config.value("initialProperties").isObject()
            || config.value("initialProperties").toObject().size() > 64))
        || (config.contains("measureObjects") && (!config.value("measureObjects").isArray()
            || config.value("measureObjects").toArray().size() > 128))
        || (!config.value("snapshot").isNull() && (!config.value("snapshot").isObject()
            || !integer(config.value("snapshot").toObject().value("maxDepth").isUndefined()
                ? QJsonValue(6) : config.value("snapshot").toObject().value("maxDepth"), 0, 16)
            || !integer(config.value("snapshot").toObject().value("maxItems").isUndefined()
                ? QJsonValue(64) : config.value("snapshot").toObject().value("maxItems"), 1, 256)))
        || (config.contains("readyProperty") && (!config.value("readyProperty").isString()
            || readyName.isEmpty() || readyName.size() > 128))) {
        std::fprintf(stderr, "Invalid renderer paths, geometry, imports or readiness property\n");
        return 1;
    }
    const int width = config.value("width").toInt();
    const int height = config.value("height").toInt();
    const int dpr = config.value("dpr").toInt();
    if (qint64(width) * height * dpr * dpr > 16000000) {
        std::fprintf(stderr, "Render exceeds pixel limit\n");
        return 1;
    }
    const QJsonArray imports = config.value("importPaths").toArray();
    for (const auto &path : imports) {
        if (!path.isString() || !QFileInfo(path.toString()).isAbsolute() || !QFileInfo(path.toString()).isDir()) {
            std::fprintf(stderr, "Invalid import directory\n");
            return 1;
        }
    }

    platform(dpr);
    if (config.contains("locale")) {
        const QString localeName = config.value("locale").toString();
        const QLocale locale(localeName);
        if (localeName.isEmpty() || (locale.language() == QLocale::C && localeName != "C")) {
            std::fprintf(stderr, "Unsupported Qt locale\n");
            return 1;
        }
        QLocale::setDefault(locale);
    }
    qInstallMessageHandler(boundedLog);
    // Do not let renderer command-line flags reach Qt's platform selection.
    int qtArgc = 1;
    QGuiApplication app(qtArgc, argv);
#ifdef QML_PREVIEW_QUICKSHELL
    initializeQuickshellPreview();
    auto *generation = createQuickshellPreview(qmlPath, imports);
    QQuickView view(generation->engine, nullptr);
#else
    QQuickView view;
#endif
    QStringList importList = view.engine()->importPathList();
    importList.removeAll(QCoreApplication::applicationDirPath());
    view.engine()->setImportPathList(importList);
    for (auto it = imports.constEnd(); it != imports.constBegin();) {
        --it;
        view.engine()->addImportPath(it->toString());
    }
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.resize(width, height);
    view.setColor(Qt::transparent);
    auto fail = [&](const QString &message) {
        qCritical("%s", qPrintable(message));
        app.exit(1);
    };
    QTimer deadline;
    deadline.setSingleShot(true);
    QObject::connect(&deadline, &QTimer::timeout, &app, [&]() { fail("Timed out waiting for QML readiness or a rendered frame"); });
    deadline.start(config.value("timeoutMs").toInt());
    view.setInitialProperties(config.value("initialProperties").toObject().toVariantMap());
    view.setSource(QUrl::fromLocalFile(qmlPath));
    if (view.status() == QQuickView::Error || !view.rootObject()) {
        for (const auto &error : view.errors())
            qCritical("%s", qPrintable(error.toString()));
        qCritical("A local QQuickItem root is required; Window/ApplicationWindow/Quickshell roots need an adapter");
        return 1;
    }
#ifdef QML_PREVIEW_QUICKSHELL
    generation->root = view.rootObject();
    generation->onReload(nullptr);
#endif
    const auto initial = config.value("initialProperties").toObject();
    for (auto it = initial.constBegin(); it != initial.constEnd(); ++it) {
        const int index = view.rootObject()->metaObject()->indexOfProperty(it.key().toUtf8().constData());
        if (index < 0 || !view.rootObject()->metaObject()->property(index).isWritable()) {
            qCritical("Invalid or read-only initial root property: %s", qPrintable(it.key()));
            return 1;
        }
    }
    QMetaProperty readyProperty;
    if (!readyName.isEmpty()) {
        const int index = view.rootObject()->metaObject()->indexOfProperty(readyName.toUtf8().constData());
        if (index < 0) {
            qCritical("Missing root readiness property: %s", qPrintable(readyName));
            return 1;
        }
        readyProperty = view.rootObject()->metaObject()->property(index);
        if (readyProperty.metaType().id() != QMetaType::Bool || !readyProperty.isReadable()) {
            qCritical("Readiness property must be a readable boolean");
            return 1;
        }
    }
    auto ready = [&]() { return readyName.isEmpty() || readyProperty.read(view.rootObject()).toBool(); };
    bool armed = false;
    bool capturing = false;
    QTimer readiness;
    readiness.setInterval(10);
    QObject::connect(&readiness, &QTimer::timeout, &app, [&]() {
        if (!armed && ready()) {
            armed = true;
            view.update();
        }
    });
    auto finishCapture = [&](const QImage &image) {
        if (!ready()) {
            armed = false;
            capturing = false;
            return;
        }
        QJsonObject measurements;
        const auto requested = config.value("measureObjects").toArray();
        QList<QQuickItem *> descendants;
        if (!requested.isEmpty() && !visualItems(view.rootObject(), descendants)) {
            fail("Visual tree exceeds 10000-item measurement limit");
            return;
        }
        for (const auto &value : requested) {
            if (!value.isString() || value.toString().isEmpty() || value.toString().size() > 128) {
                fail("Invalid measurement objectName");
                return;
            }
            const QString name = value.toString();
            QList<QObject *> matches;
            for (auto *object : descendants) {
                if (object->objectName() == name)
                    matches.append(object);
            }
            if (matches.size() != 1 || !qobject_cast<QQuickItem *>(matches.value(0))) {
                if (!config.value("requiredMeasureObjects").toArray().contains(name))
                    continue; // Missing/ambiguous assertion targets become explicit FAIL results.
                fail("Measurement requires exactly one visual QQuickItem named: " + name);
                return;
            }
            auto *item = qobject_cast<QQuickItem *>(matches[0]);
            const auto measured = geometry(item);
            if (measured.isEmpty()) {
                fail("Measurement geometry must be finite: " + name);
                return;
            }
            measurements.insert(name, measured);
        }
        if (image.isNull() || image.size() != QSize(width * dpr, height * dpr)
            || view.effectiveDevicePixelRatio() != dpr) {
            fail(QString("Empty image or unsupported physical geometry/DPR: got %1x%2 at DPR %3, requested %4x%5 at DPR %6")
                 .arg(image.width()).arg(image.height()).arg(view.effectiveDevicePixelRatio())
                 .arg(width * dpr).arg(height * dpr).arg(dpr));
            return;
        }
        QFile output;
        if (!output.open(outputFd, QIODevice::ReadWrite, QFileDevice::DontCloseHandle)
            || !image.save(&output, "PNG") || !output.flush() || !output.seek(0)) {
            fail("Failed to write PNG to the inherited descriptor");
            return;
        }
        QImageReader reader(&output, "PNG");
        const QImage decoded = reader.read();
        if (decoded.isNull() || decoded.size() != image.size() || output.size() > 64 * 1024 * 1024) {
            fail("PNG decode verification failed or output exceeds 64 MiB");
            return;
        }
        QJsonObject metadata {
            {"pixelWidth", decoded.width()}, {"pixelHeight", decoded.height()},
            {"dpr", view.effectiveDevicePixelRatio()}, {"backend", "software"},
            {"platform", QGuiApplication::platformName()}, {"qtVersion", qVersion()},
            {"rendererVersion", version}, {"measurements", measurements},
            {"captureMethod", "QQuickItem::grabToImage"},
#ifdef QML_PREVIEW_QUICKSHELL
            {"hostAdapter", "Quickshell static modules; offscreen, no compositor or shell IPC"},
#endif
            {"qtImportPaths", QJsonArray::fromStringList(view.engine()->importPathList())},
            {"locale", QLocale().name()}, {"fontFamily", app.font().family()},
            {"fontPointSize", app.font().pointSizeF()},
            {"readyProperty", readyName.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(readyName)},
            {"readiness", readyName.isEmpty() ? "loaded-frame" : "property-and-frame"},
            {"capturedAt", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)}
        };
        if (config.value("snapshot").isObject())
            metadata.insert("snapshot", snapshot(view.rootObject(), config.value("snapshot").toObject()));
        if (QJsonDocument(metadata).toJson(QJsonDocument::Compact).size() > metadataLimit) {
            fail("Renderer metadata exceeds 512 KiB limit");
            return;
        }
        jsonOutput(metadata);
        app.quit();
    };
    QSharedPointer<QQuickItemGrabResult> grabResult;
    std::function<void(const QSize &)> grab;
    grab = [&](const QSize &target) {
        grabResult = view.rootObject()->grabToImage(target);
        if (!grabResult) {
            fail("Failed to initiate QQuickItem offscreen image capture");
            return;
        }
        QObject::connect(grabResult.data(), &QQuickItemGrabResult::ready, &app, [&, target]() {
            const QImage image = grabResult->image();
            // Qt releases differ in whether targetSize is multiplied by DPR.
            // If necessary, redraw once into a physical target, never resize pixels.
            if (dpr == 2 && target == QSize(width, height) && image.size() == target) {
                QTimer::singleShot(0, &app, [&]() { grab(QSize(width * dpr, height * dpr)); });
                return;
            }
            finishCapture(image);
        });
    };
    QObject::connect(&view, &QQuickWindow::frameSwapped, &app, [&]() {
        if (!armed || capturing)
            return;
        if (!ready()) {
            armed = false;
            return;
        }
        capturing = true;
        // Native layer redraw, not raster resizing. Qt 6.2's software backing
        // store grabWindow does not reliably preserve DPR on offscreen QPA.
        grab(QSize(width, height));
    }, Qt::QueuedConnection);
    QObject::connect(&view, &QQuickWindow::sceneGraphError, &app,
                     [&](QQuickWindow::SceneGraphError, const QString &message) { fail(message); });
    readiness.start();
    view.show(); // QT_QPA_PLATFORM is forced to offscreen before app construction.
    const int result = app.exec();
#ifdef QML_PREVIEW_QUICKSHELL
    // Let the host's generation own its root/engine cleanup before view teardown.
    generation->shutdown();
#endif
    return result;
}
