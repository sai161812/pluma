using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI;

internal static class EventNoticePresentation
{
    internal static ToastNotification Create(EventFeedEntry entry)
    {
        var notice = new ToastNotification();
        notice.Show(entry.DisplayText, entry.Warning ? InfoBarSeverity.Warning
            : entry.Verified ? InfoBarSeverity.Success : InfoBarSeverity.Informational);
        return notice;
    }
}
