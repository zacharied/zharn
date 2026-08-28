import QtQuick

// Every content component derives from this so a TabGroup can inject tabKey/tabTitle.
Item {
    property string tabKey: ""
    property string tabTitle: ""
}
