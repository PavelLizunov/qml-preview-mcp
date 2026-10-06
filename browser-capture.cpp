// Optional in-process bridge. One fixed plugin/primary-view endpoint, no evaluator.
#include <QQmlExtensionPlugin>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickWindow>
#include <QQuickItemGrabResult>
#include <QLocalServer>
#include <QLocalSocket>
#include <QTimer>
#include <QPointer>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QCryptographicHash>
#include <QJsonDocument>
#include <QJsonObject>
#include <QBuffer>
#include <QDateTime>
#include <QtEndian>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>
#include <cmath>
#include "hidden-browser-render.hpp"

class BrowserCapture : public QObject {
    Q_OBJECT
    Q_PROPERTY(QQuickItem* browser READ browser WRITE setBrowser NOTIFY browserChanged)
    Q_PROPERTY(bool presented MEMBER presented NOTIFY presentedChanged)
    Q_PROPERTY(bool enabled READ enabled WRITE setEnabled NOTIFY enabledChanged)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(QUrl ownerSource MEMBER ownerSource)
public:
    using QObject::QObject;
    ~BrowserCapture() override {
        if (hiddenJob) { hiddenJob->abandon(); delete hiddenJob.data(); }
        server.close(); if (ownsSocket) QFile::remove(endpoint);
    }
    QQuickItem *browser() const { return item; }
    void setBrowser(QQuickItem *value) { item = value; emit browserChanged(); }
    bool enabled() const { return server.isListening(); }
    QString error() const { return lastError; }
    bool presented = false;
    QUrl ownerSource;
    void setEnabled(bool value) {
        if (!value) {
            if (hiddenJob) hiddenJob->cancel();
            server.close(); if (ownsSocket) QFile::remove(endpoint); ownsSocket = false; emit enabledChanged(); return;
        }
        if (enabled()) return;
        const QString runtime = QString("/run/user/%1").arg(getuid());
        #ifdef QML_CAPTURE_INERT_TEST
        const QString directory = runtime + "/qml-preview-slovn.chatgpt-lite-hidden-test";
#else
        const QString directory = runtime + "/qml-preview-slovn.chatgpt-lite";
#endif
        // No ambient runtime path or caller-controlled filesystem operand.
        endpoint = directory + "/capture.sock";
        struct stat st {};
        auto secure = [&](const QString &path) {
            return ::lstat(QFile::encodeName(path).constData(), &st) == 0 && S_ISDIR(st.st_mode)
                && st.st_uid == getuid() && (st.st_mode & 0777) == 0700;
        };
        if (!secure(runtime)) { fail("RUNTIME_UNSAFE"); return; }
        if (::mkdir(QFile::encodeName(directory).constData(), 0700) != 0 && errno != EEXIST) { fail("RUNTIME_UNSAFE"); return; }
        if (!secure(directory) || ::lstat(QFile::encodeName(endpoint).constData(), &st) == 0) { fail("ENDPOINT_UNSAFE_OR_BUSY"); return; }
        server.setSocketOptions(QLocalServer::UserAccessOption);
        server.setMaxPendingConnections(1);
        if (!server.listen(endpoint)) { fail("LISTEN_FAILED"); return; }
        ownsSocket = true;
        if (::chmod(QFile::encodeName(endpoint).constData(), 0600) != 0) { setEnabled(false); fail("ENDPOINT_UNSAFE"); return; }
        connect(&server, &QLocalServer::newConnection, this, &BrowserCapture::accept, Qt::UniqueConnection);
        emit enabledChanged();
    }
signals:
    void browserChanged();
    void presentedChanged();
    void enabledChanged();
    void errorChanged();
    void captured();
private:
    QPointer<QQuickItem> item;
    QPointer<HiddenBrowserRender> hiddenJob;
    QLocalServer server;
    QString endpoint, lastError;
    bool ownsSocket = false, busy = false;
    int activeConnections = 0;
    void fail(const QString &code) { lastError = code; emit errorChanged(); }
    QJsonObject hashes() const {
        if (!ownerSource.isLocalFile() || QFileInfo(ownerSource.toLocalFile()).fileName() != "Capture.qml") return {};
        const QString base = QFileInfo(ownerSource.toLocalFile()).absolutePath();
        const QString home = QDir::homePath();
        const QString reference = home + "/Work/omarchy-plugins/omarchy-chatgpt-lite/native";
        const QString installed = home + "/.config/omarchy/plugins/slovn.chatgpt-lite/native";
        if (base != reference && base != installed) return {};
        QJsonObject result;
        for (const QString &name : {QString("Service.qml"), QString("Content.qml"), QString("Browser.qml"), QString("Theme.js"), QString("Capture.qml")}) {
            QFileInfo info(base + "/" + name);
            if (!info.isFile() || info.isSymLink() || info.canonicalFilePath() != info.absoluteFilePath() || info.size() > 16 * 1024 * 1024) return {};
            QFile file(info.absoluteFilePath());
            if (!file.open(QIODevice::ReadOnly)) return {};
            result.insert(info.absoluteFilePath(), QString::fromLatin1(QCryptographicHash::hash(file.readAll(), QCryptographicHash::Sha256).toHex()));
        }
        return result;
    }
    void reply(QLocalSocket *socket, const QJsonObject &metadata, const QByteArray &png = {}) {
        const auto json = QJsonDocument(metadata).toJson(QJsonDocument::Compact);
        QByteArray header(8, '\0');
        qToBigEndian<quint32>(json.size(), reinterpret_cast<uchar*>(header.data()));
        qToBigEndian<quint32>(png.size(), reinterpret_cast<uchar*>(header.data() + 4));
        socket->write(header); socket->write(json); socket->write(png);
        socket->disconnectFromServer();
    }
    void reject(QLocalSocket *socket, const QString &code) { reply(socket, {{"error", QJsonObject{{"code", code}}}}); }
    void publishImage(QLocalSocket *peer, const QImage &image, const QJsonObject &before,
                      double dpr, QSize logical, QSize pixels, bool fixture, bool hidden) {
        if (image.isNull() || image.size() != pixels) { reject(peer, "PIXELS_UNSUPPORTED"); return; }
        QByteArray png; QBuffer buffer(&png); buffer.open(QIODevice::WriteOnly);
        if (!image.save(&buffer, "PNG") || png.size() > 64 * 1024 * 1024 || QImage::fromData(png, "PNG").size() != image.size()) { reject(peer, "PNG_FAILED"); return; }
        reply(peer, {{"pluginId", "slovn.chatgpt-lite"}, {"target", "primary-browser"},
            {"captureKind", "current-browser-item"}, {"pageKind", fixture ? "inert-local-fixture" : "account-capable-live-page"},
            {"captureMethod", hidden ? "QQuickRenderControl::offscreen" : "QQuickItem::grabToImage"},
            {"width", logical.width()}, {"height", logical.height()},
            {"pixelWidth", image.width()}, {"pixelHeight", image.height()}, {"dpr", dpr},
            {"capturedAt", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)},
            {"readiness", "navigation-succeeded-and-item-grab; page-settled-unknown"}, {"pageSettled", QJsonValue::Null},
            {"consumerPid", int(getpid())}, {"qtVersion", qVersion()}, {"sourceHashes", before},
            {"interactionVerified", false}, {"liveSiteVerified", false}}, png);
        emit captured();
    }
    void accept() {
        auto *socket = server.nextPendingConnection();
        if (!socket) return;
        struct ucred credentials {}; socklen_t length = sizeof(credentials);
        if (::getsockopt(socket->socketDescriptor(), SOL_SOCKET, SO_PEERCRED, &credentials, &length) != 0 || credentials.uid != getuid()) { socket->abort(); socket->deleteLater(); return; }
        if (activeConnections >= 1) { socket->abort(); socket->deleteLater(); return; }
        ++activeConnections;
        connect(socket, &QObject::destroyed, this, [this]() { --activeConnections; });
        socket->setReadBufferSize(1025);
        auto *timer = new QTimer(socket); timer->setSingleShot(true); timer->start(5000);
        connect(timer, &QTimer::timeout, socket, [this, socket]() { reject(socket, "TIMEOUT"); socket->abort(); });
        connect(socket, &QLocalSocket::disconnected, socket, &QObject::deleteLater);
        auto input = QSharedPointer<QByteArray>::create();
        auto handled = QSharedPointer<bool>::create(false);
        connect(socket, &QLocalSocket::readyRead, socket, [this, socket, input, handled]() {
            if (*handled) { socket->abort(); return; }
            input->append(socket->readAll());
            if (input->size() > 1024) { *handled = true; reject(socket, "BAD_REQUEST"); return; }
            if (!input->endsWith('\n')) return;
            *handled = true;
            QJsonParseError parse;
            const auto doc = QJsonDocument::fromJson(*input, &parse);
            const auto request = doc.object();
            if (parse.error != QJsonParseError::NoError || !doc.isObject() || request.size() != 3
                || request.value("operation") != "capture" || request.value("pluginId") != "slovn.chatgpt-lite"
                || request.value("consent") != "local-account-image") { reject(socket, "ADMISSION_DENIED"); return; }
            if (busy) { reject(socket, "BUSY"); return; }
            auto *view = item.data();
            bool webEngine = false;
            if (view) for (auto *meta = view->metaObject(); meta; meta = meta->superClass())
                if (QByteArray(meta->className()) == "QQuickWebEngineView") webEngine = true;
            // qmlContext(view) is the instantiation context (Content or the
            // reviewed fixture), not Browser.qml; admission belongs to the
            // fixed Capture.qml owner and its explicit primary-view pointer.
            if (!webEngine || view->objectName() != "chatgptBrowser") { reject(socket, "CONSUMER_UNAVAILABLE"); return; }
            if (!view->window()) { reject(socket, "CONSUMER_UNAVAILABLE"); return; }
            const bool hidden = !presented && !view->window()->isVisible();
            if (!hidden && (!presented || !view->isVisible() || !view->window()->isVisible())) { reject(socket, "HIDDEN_UNSUPPORTED"); return; }
            if (view->property("loadState").toString() != "SUCCEEDED" || view->property("loading").toBool()) { reject(socket, "PAGE_NOT_READY"); return; }
            const bool fixture = view->property("fixtureMode").toBool();
            // Classify without exporting URLs. Do not inspect login, DOM or storage.
            if (!fixture && view->property("url").toUrl().host() != "chatgpt.com") { reject(socket, "PAGE_NOT_ALLOWLISTED"); return; }
            const auto before = hashes();
            if (before.isEmpty()) { reject(socket, "SOURCE_IDENTITY_UNAVAILABLE"); return; }
            const double dpr = view->window()->effectiveDevicePixelRatio();
            const QSize logical(qRound(view->width()), qRound(view->height()));
            const QSize pixels(qRound(logical.width() * dpr), qRound(logical.height() * dpr));
            if (!std::isfinite(dpr) || dpr <= 0 || dpr > 4 || logical.isEmpty() || pixels.width() > 8192 || pixels.height() > 8192
                || qint64(pixels.width()) * pixels.height() > 16000000) { reject(socket, "GEOMETRY_UNSUPPORTED"); return; }
            if (hidden) {
                // Never resume or alter lifecycle to manufacture capture readiness.
                if (view->property("lifecycleState").toInt() != 0) { reject(socket, "PAGE_NOT_READY"); return; }
                busy = true;
                QPointer<QLocalSocket> peer(socket);
                QPointer<QQuickItem> target(view);
                auto *render = new HiddenBrowserRender(view, logical, dpr, this);
                hiddenJob = render;
                connect(socket, &QLocalSocket::disconnected, render, [render]() { render->cancel(); });
                render->start([this, peer, target, before, dpr, logical, pixels, fixture](QImage image, QString code) {
                    busy = false;
                    hiddenJob.clear();
                    if (!peer || peer->state() != QLocalSocket::ConnectedState) return;
                    if (!code.isEmpty()) { reject(peer, code); return; }
                    if (!enabled() || !target || target != item || presented || !target->window()
                        || target->window()->isVisible() || hashes() != before
                        || target->property("loading").toBool() || target->property("loadState").toString() != "SUCCEEDED"
                        || target->window()->effectiveDevicePixelRatio() != dpr
                        || qRound(target->width()) != logical.width() || qRound(target->height()) != logical.height()) {
                        reject(peer, "CONSUMER_CHANGED"); return;
                    }
                    publishImage(peer, image, before, dpr, logical, pixels, fixture, true);
                });
                return;
            }
            busy = true;
            auto grab = view->grabToImage(logical);
            if (!grab) { busy = false; reject(socket, "GRAB_UNSUPPORTED"); return; }
            // Retain only one owned grab until ready or deadline. Context-bound
            // callbacks and QPointers reject stale/disconnected/destroyed targets.
            auto *job = new QObject(this);
            auto *limit = new QTimer(job); limit->setSingleShot(true); limit->start(4000);
            connect(limit, &QTimer::timeout, job, [this, job, grab]() { busy = false; job->deleteLater(); });
            QPointer<QLocalSocket> peer(socket); QPointer<QQuickItem> target(view);
            connect(grab.data(), &QQuickItemGrabResult::ready, job, [this, job, peer, target, grab, before, dpr, logical, pixels, fixture]() {
                busy = false; job->deleteLater();
                if (!peer || peer->state() != QLocalSocket::ConnectedState) return;
                if (!enabled() || target != item || !target || !presented || !target->isVisible() || !target->window() || !target->window()->isVisible()
                    || target->property("loadState").toString() != "SUCCEEDED" || target->property("loading").toBool()
                    || hashes() != before || target->window()->effectiveDevicePixelRatio() != dpr
                    || qRound(target->width()) != logical.width() || qRound(target->height()) != logical.height()) { reject(peer, "CONSUMER_CHANGED"); return; }
                publishImage(peer, grab->image(), before, dpr, logical, pixels, fixture, false);
            });
        });
    }
};

class CapturePlugin : public QQmlExtensionPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override { qmlRegisterType<BrowserCapture>(uri, 1, 0, "BrowserCapture"); }
};
#include "browser-capture.moc"
