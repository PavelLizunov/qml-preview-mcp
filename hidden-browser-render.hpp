// Fixed bridge-internal, bounded render of the existing primary item only.
// No platform window is created/shown and no input or focus request is issued.
#pragma once
#include <QQuickRenderControl>
#include <QQuickRenderTarget>
#include <QSGRendererInterface>
#include <QGuiApplication>
#include <rhi/qrhi.h>
#include <functional>
#include <memory>

class HiddenBrowserRender : public QObject {
public:
    HiddenBrowserRender(QQuickItem *view, QSize logical, double dpr, QObject *owner)
        : QObject(owner), target(view), originalParent(view->parentItem()),
          originalWindow(view->window()), originalFocus(QGuiApplication::focusWindow()),
          originalRect(view->x(), view->y(), view->width(), view->height()),
          rendererPid(view->property("renderProcessPid")), size(logical), scale(dpr) {}
    ~HiddenBrowserRender() override { restore(); }
    void start(std::function<void(QImage, QString)> done) {
        complete = std::move(done);
        control = std::make_unique<QQuickRenderControl>();
        window = std::make_unique<QQuickWindow>(control.get());
        window->setGeometry(0, 0, size.width(), size.height());
        window->setColor(Qt::transparent);
        window->contentItem()->setVisible(true);
        window->contentItem()->setSize(QSizeF(size));
        const QSize pixels(qRound(size.width() * scale), qRound(size.height() * scale));
        auto *backendWindow = originalWindow.data();
        if (!backendWindow) backendWindow = qobject_cast<QQuickWindow *>(QGuiApplication::focusWindow());
        // Backend metadata only; never read another window's items or pixels.
        software = backendWindow && backendWindow->rendererInterface()->graphicsApi() == QSGRendererInterface::Software;
        if (qgetenv("QT_QUICK_BACKEND") == "software") software = true;
        if (software) {
            image = QImage(pixels, QImage::Format_ARGB32_Premultiplied);
            image.setDevicePixelRatio(scale);
            image.fill(Qt::transparent);
            auto rt = QQuickRenderTarget::fromPaintDevice(&image);
            rt.setDevicePixelRatio(scale);
            window->setRenderTarget(rt);
        } else {
            if (!control->initialize() || !control->rhi()) { finish({}, "OFFSCREEN_UNSUPPORTED"); return; }
            auto *rhi = control->rhi();
            texture.reset(rhi->newTexture(QRhiTexture::RGBA8, pixels, 1,
                QRhiTexture::RenderTarget | QRhiTexture::UsedAsTransferSource));
            if (!texture->create()) { finish({}, "OFFSCREEN_UNSUPPORTED"); return; }
            QRhiTextureRenderTargetDescription desc{QRhiColorAttachment(texture.get())};
            renderTarget.reset(rhi->newTextureRenderTarget(desc));
            pass.reset(renderTarget->newCompatibleRenderPassDescriptor());
            renderTarget->setRenderPassDescriptor(pass.get());
            if (!renderTarget->create()) { finish({}, "OFFSCREEN_UNSUPPORTED"); return; }
            auto rt = QQuickRenderTarget::fromRhiRenderTarget(renderTarget.get());
            rt.setDevicePixelRatio(scale);
            window->setRenderTarget(rt);
        }
        // QObject/profile ownership stays in Service; only visual parenting moves.
        target->setParentItem(window->contentItem());
        target->setPosition(QPointF(0, 0));
        moved = true;
        tick.setInterval(40);
        connect(&tick, &QTimer::timeout, this, [this]() { frame(); });
        tick.start();
        frame();
    }
    void cancel() { finish({}, "CONSUMER_CHANGED"); }
    void abandon() { complete = {}; finished = true; restore(); }
private:
    QPointer<QQuickItem> target, originalParent;
    QPointer<QQuickWindow> originalWindow;
    QPointer<QWindow> originalFocus;
    QRectF originalRect;
    QVariant rendererPid;
    QSize size;
    double scale;
    bool software = false, moved = false, finished = false;
    int frames = 0;
    QTimer tick;
    QImage image;
    std::unique_ptr<QQuickRenderControl> control;
    std::unique_ptr<QQuickWindow> window;
    std::unique_ptr<QRhiTexture> texture;
    std::unique_ptr<QRhiTextureRenderTarget> renderTarget;
    std::unique_ptr<QRhiRenderPassDescriptor> pass;
    QRhiReadbackResult readback;
    std::function<void(QImage, QString)> complete;
    void restore() {
        tick.stop();
        if (moved && target && window && target->parentItem() == window->contentItem()) {
            target->setParentItem(originalParent);
            target->setPosition(originalRect.topLeft());
            target->setSize(originalRect.size());
        }
        moved = false;
        if (control) control->invalidate();
        if (window) window->setRenderTarget({});
        renderTarget.reset(); pass.reset(); texture.reset();
        window.reset(); control.reset();
    }
    void finish(QImage result, const QString &error) {
        if (finished) return;
        finished = true;
        restore();
        auto callback = std::move(complete);
        if (callback) callback(std::move(result), error);
        deleteLater();
    }
    void frame() {
        if (!target || !originalParent || (originalWindow && originalWindow->isVisible())
            || QGuiApplication::focusWindow() != originalFocus || window->isVisible()
            || window->handle() || target->property("renderProcessPid") != rendererPid
            || target->property("loading").toBool()
            || target->property("loadState").toString() != "SUCCEEDED"
            || target->parentItem() != window->contentItem()
            || target->property("lifecycleState").toInt() != 0
            || target->size() != QSizeF(size)) {
#ifdef QML_CAPTURE_INERT_TEST
            qWarning("inert hidden guard: parent=%d window=%d original-visible=%d focus-changed=%d offscreen-visible=%d handle=%d pid-changed=%d loading=%d size-changed=%d",
                bool(originalParent), bool(originalWindow), originalWindow && originalWindow->isVisible(),
                QGuiApplication::focusWindow() != originalFocus, window->isVisible(), bool(window->handle()),
                target && target->property("renderProcessPid") != rendererPid, target && target->property("loading").toBool(),
                target && target->size() != QSizeF(size));
#endif
            finish({}, "CONSUMER_CHANGED"); return;
        }
        if (++frames > 12) { finish({}, "TIMEOUT"); return; }
        control->polishItems();
        if (!software) control->beginFrame();
        control->sync();
        control->render();
        if (!software) {
            // Exactly one readback at a finite paint allowance, never until PASS.
            if (frames == 10) {
                auto *updates = control->rhi()->nextResourceUpdateBatch();
                updates->readBackTexture(QRhiReadbackDescription(texture.get()), &readback);
                control->commandBuffer()->resourceUpdate(updates);
            }
            control->endFrame();
        }
        if (frames != 10) return;
        if (software) { finish(image.copy(), {}); return; }
        if (readback.data.isEmpty()) { finish({}, "PIXELS_UNSUPPORTED"); return; }
        QImage result(reinterpret_cast<const uchar *>(readback.data.constData()),
            readback.pixelSize.width(), readback.pixelSize.height(), QImage::Format_RGBA8888);
        auto copy = result.copy();
        if (control->rhi()->isYUpInFramebuffer()) copy = copy.flipped(Qt::Vertical);
        copy.setDevicePixelRatio(scale);
        finish(copy, {});
    }
};
