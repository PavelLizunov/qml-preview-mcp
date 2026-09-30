import QtQuick

Rectangle {
    id: root
    objectName: "consumer"
    color: "#182028"
    property bool previewReady: false
    property string fixtureTitle: "QML preview fixture"
    property string fixtureState: "Fixture ready"

    // A real component is loaded by this consumer, with an inert fixture model.
    QtObject {
        id: model
        property string title: root.fixtureTitle
        property string state: root.previewReady ? root.fixtureState : "Loading fixture"
    }

    Timer {
        interval: 80
        running: true
        onTriggered: root.previewReady = true
    }

    FixturePanel {
        anchors.fill: parent
        anchors.margins: 20
        fixtureModel: model
    }
}
