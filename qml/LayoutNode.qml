import QtQuick
import QtQuick.Controls.Basic

// Recursive renderer for the center tree: split → SplitView of LayoutNodes, tabs → TabGroup.
Item {
    id: nodeItem
    property var node

    Loader {
        anchors.fill: parent
        sourceComponent: nodeItem.node && nodeItem.node.type === "split" ? splitComp : tabsComp
    }

    Component {
        id: tabsComp
        TabGroup { node: nodeItem.node }
    }

    Component {
        id: splitComp
        SplitView {
            id: sv
            objectName: "split_" + nodeItem.node.id
            orientation: nodeItem.node.orientation === "horizontal" ? Qt.Horizontal : Qt.Vertical
            handle: SplitGrip {}
            Repeater {
                model: nodeItem.node.children
                delegate: Loader {  // runtime URL: QML forbids static self-recursion
                    required property int index
                    required property var modelData
                    Component.onCompleted: setSource("LayoutNode.qml", { node: modelData })
                    SplitView.preferredWidth: sv.width * nodeItem.node.ratios[index]
                    SplitView.preferredHeight: sv.height * nodeItem.node.ratios[index]
                    SplitView.fillWidth: index === nodeItem.node.children.length - 1
                    SplitView.fillHeight: index === nodeItem.node.children.length - 1
                    SplitView.minimumWidth: 80; SplitView.minimumHeight: 60
                }
            }
            onResizingChanged: if (!resizing) {
                var horizontal = orientation === Qt.Horizontal, ratios = []
                for (var i = 0; i < sv.contentChildren.length; i++) {
                    var c = sv.contentChildren[i]
                    ratios.push(horizontal ? c.width : c.height)
                }
                app.layout.setRatios(nodeItem.node.id, ratios)
            }
        }
    }
}
