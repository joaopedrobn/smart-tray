import QtQuick
import QtQuick.Controls

ScrollView {
    id: scroll
    clip: true
    readonly property int cardPadding: 20
    // A permanent gutter keeps the scrollbar outside all text and controls.
    rightPadding: 16
    bottomPadding: 8
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical: DarkScrollBar { objectName: scroll.objectName + "Bar" }
}
