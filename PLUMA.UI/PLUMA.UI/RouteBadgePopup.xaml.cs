using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class RouteBadgePopup : UserControl
    {
        public static readonly DependencyProperty RouteProperty = DependencyProperty.Register(
            nameof(Route), typeof(string), typeof(RouteBadgePopup), new PropertyMetadata(string.Empty,
                (sender, _) => ((RouteBadgePopup)sender).RefreshRoute()));
        public string Route { get => (string)GetValue(RouteProperty); set => SetValue(RouteProperty, value); }
        public RouteBadgePopup()
        {
            InitializeComponent();
            RefreshRoute();
        }
        private void RefreshRoute()
        {
            if (RouteText is not null) RouteText.Text = Route switch
            { "FAST" => "Fast", "SMART" => "Smart", "SCREEN" => "Screen", "DEEP" => "Deep", _ => "Unavailable" };
        }
    }
}
