import QtQuick

Rectangle {
    id: root
    objectName: "canvas"
    color: "#182028"
    property real rightOffset: 0
    property bool previewReady: true

    Rectangle {
        objectName: "frame"
        anchors.fill: parent
        anchors.margins: 20
        color: "#25313c"
        border.color: "#71c7a0"
        Rectangle {
            objectName: "left"
            x: 20; y: 90; width: 80; height: 40
            color: "#71c7a0"
        }
        Rectangle {
            objectName: "right"
            x: parent.width - 100 + root.rightOffset
            y: 90; width: 80; height: 40
            color: "#71c7a0"
        }
        Text {
            objectName: "heading"
            anchors.horizontalCenter: parent.horizontalCenter
            y: 20
            text: "Geometry fixture"
            textFormat: Text.PlainText
            color: "#f0f4f8"
            font.family: "DejaVu Sans"
            font.pixelSize: 20
        }
    }
    Component.onCompleted: {
        // QObject owner stays root while visual parent becomes frame.
        const item = detached.createObject(root)
        item.parent = root.children[0]
    }
    Component {
        id: detached
        Rectangle { objectName: "reparented"; x: 20; y: 180; width: 20; height: 20; color: "#f0f4f8" }
    }
}
