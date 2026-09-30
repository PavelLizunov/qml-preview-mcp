import QtQuick
import FixturePalette

Rectangle {
    objectName: "panel"
    required property QtObject fixtureModel
    color: "#25313c"
    border.color: Colors.accent
    border.width: 2
    radius: 8

    Text {
        objectName: "title"
        x: 20
        y: 20
        text: fixtureModel.title
        textFormat: Text.PlainText
        color: "#f0f4f8"
        font.family: "DejaVu Sans"
        font.pixelSize: 22
    }
    Text {
        objectName: "status"
        x: 20
        y: 60
        text: fixtureModel.state
        textFormat: Text.PlainText
        color: "#f0f4f8"
        font.family: "DejaVu Sans"
        font.pixelSize: 16
    }
    Rectangle {
        objectName: "accent"
        x: 20
        y: 110
        width: parent.width - 40
        height: 40
        color: Colors.accent
    }
    Text {
        x: 20
        y: 170
        text: "Inert model / offscreen / software"
        color: "#f0f4f8"
        font.family: "DejaVu Sans"
        font.pixelSize: 14
    }
}
