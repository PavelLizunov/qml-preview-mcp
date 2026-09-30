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
#include <QQuickView>
#include <QSet>
#include <QTimer>
#include <cmath>
#include <atomic>
#include <cstdio>
#include <cstdlib>

static constexpr auto version = "0.2.0";

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

static void boundedLog(QtMsgType type, const QMessageLogContext &, const QString &message) {
    static std::atomic<int> remaining {65536};
    const QByteArray bytes = message.left(16384).toUtf8() + '\n';
    const int count = qBound(0, remaining.fetch_sub(bytes.size()), int(bytes.size()));
    if (count > 0) {
        std::fwrite(bytes.constData(), 1, count, stderr);
    }
    if (type == QtFatalMsg)
        std::abort();
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
        paths.removeAll(QCoreApplication::applicationDirPath());
        jsonOutput({{"rendererVersion", version}, {"qtVersion", qVersion()},
                    {"platform", QGuiApplication::platformName()}, {"backend", "software"},
                    {"qtImportPaths", QJsonArray::fromStringList(paths)},
                    {"rootTypes", QJsonArray {"QQuickItem", "Item", "Rectangle"}},
                    {"supportedDpr", QJsonArray {1, 2}}, {"interaction", false},
                    {"qmlExecuted", false}, {"shaderEffects", false}});
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
    const QString qmlPath = config.value("qmlPath").toString();
    const QString readyName = config.value("readyProperty").toString();
    if (!QFileInfo(qmlPath).isAbsolute() || !QFileInfo(qmlPath).isFile()
        || !integer(config.value("width"), 1, 4096) || !integer(config.value("height"), 1, 4096)
        || !integer(config.value("dpr"), 1, 2) || !integer(config.value("timeoutMs"), 100, 10000)
        || !config.value("importPaths").isArray() || config.value("importPaths").toArray().size() > 32
        || (config.contains("initialProperties") && (!config.value("initialProperties").isObject()
            || config.value("initialProperties").toObject().size() > 64))
        || (config.contains("measureObjects") && (!config.value("measureObjects").isArray()
            || config.value("measureObjects").toArray().size() > 64))
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
    QQuickView view;
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
    QObject::connect(&view, &QQuickWindow::frameSwapped, &app, [&]() {
        if (!armed || capturing)
            return;
        if (!ready()) {
            armed = false;
            return;
        }
        capturing = true;
        QJsonObject measurements;
        const auto requested = config.value("measureObjects").toArray();
        const auto descendants = view.rootObject()->findChildren<QObject *>();
        for (const auto &value : requested) {
            if (!value.isString() || value.toString().isEmpty() || value.toString().size() > 128) {
                fail("Invalid measurement objectName");
                return;
            }
            const QString name = value.toString();
            QList<QObject *> matches;
            if (view.rootObject()->objectName() == name)
                matches.append(view.rootObject());
            for (auto *object : descendants) {
                if (object->objectName() == name)
                    matches.append(object);
            }
            if (matches.size() != 1 || !qobject_cast<QQuickItem *>(matches.value(0))) {
                fail("Measurement requires exactly one visual QQuickItem named: " + name);
                return;
            }
            auto *item = qobject_cast<QQuickItem *>(matches[0]);
            const QRectF bounds = item->mapRectToScene(QRectF(0, 0, item->width(), item->height()));
            const QList<double> geometry {bounds.x(), bounds.y(), bounds.width(), bounds.height(),
                                          item->implicitWidth(), item->implicitHeight()};
            for (double number : geometry) {
                if (!std::isfinite(number)) {
                    fail("Measurement geometry must be finite: " + name);
                    return;
                }
            }
            measurements.insert(name, QJsonObject {
                {"x", bounds.x()}, {"y", bounds.y()}, {"width", bounds.width()}, {"height", bounds.height()},
                {"implicitWidth", item->implicitWidth()}, {"implicitHeight", item->implicitHeight()},
                {"visible", item->isVisible()}, {"enabled", item->isEnabled()},
                {"clip", item->clip()}, {"activeFocus", item->hasActiveFocus()},
                {"coordinateSpace", "logical-scene-axis-aligned"}
            });
        }
        // The queued callback runs on the GUI thread after a completed frame.
        const QImage image = view.grabWindow();
        if (image.isNull() || image.size() != QSize(width * dpr, height * dpr)
            || view.effectiveDevicePixelRatio() != dpr) {
            fail("Empty image or unsupported physical geometry/DPR");
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
        const QJsonObject metadata {
            {"pixelWidth", decoded.width()}, {"pixelHeight", decoded.height()},
            {"dpr", view.effectiveDevicePixelRatio()}, {"backend", "software"},
            {"platform", QGuiApplication::platformName()}, {"qtVersion", qVersion()},
            {"rendererVersion", version}, {"measurements", measurements},
            {"qtImportPaths", QJsonArray::fromStringList(view.engine()->importPathList())},
            {"locale", QLocale().name()}, {"fontFamily", app.font().family()},
            {"fontPointSize", app.font().pointSizeF()},
            {"readyProperty", readyName.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(readyName)},
            {"readiness", readyName.isEmpty() ? "loaded-frame" : "property-and-frame"},
            {"capturedAt", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)}
        };
        jsonOutput(metadata);
        app.quit();
    }, Qt::QueuedConnection);
    QObject::connect(&view, &QQuickWindow::sceneGraphError, &app,
                     [&](QQuickWindow::SceneGraphError, const QString &message) { fail(message); });
    readiness.start();
    view.show(); // QT_QPA_PLATFORM is forced to offscreen before app construction.
    return app.exec();
}
