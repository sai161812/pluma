using PLUMA.UI;

int checks = 0;
void Check(bool condition, string name)
{
    if (!condition) throw new InvalidOperationException(name);
    checks++;
}
PopupDesktop Desktop(double scale = 1, double x = 0, double y = 0) => new(new(x, y, 1920, 1080), new(x, y, 1920, 1032), scale, Array.Empty<PopupAppBar>());
var state = new PopupStackState();
state.Upsert("A", 360, 140, false, TimeSpan.FromSeconds(4));
state.Upsert("B", 420, 150, false, TimeSpan.FromSeconds(4));
state.Upsert("C", 220, 80, false, TimeSpan.FromSeconds(2));
var plan = state.Plan(Desktop());
Check(plan.Placements.Select(p => p.Key).SequenceEqual(new[] { "A", "B", "C" }), "oldest to newest order");
Check(plan.Placements[0].Bounds.Y < plan.Placements[1].Bounds.Y && plan.Placements[1].Bounds.Y < plan.Placements[2].Bounds.Y, "newest is lowest");
Check(plan.Placements.Select(p => p.Bounds.Right).Distinct().Count() == 1, "common right edge for different widths");
state.Upsert("B", 420, 180, false, TimeSpan.FromSeconds(5));
Check(state.Items.Count == 3 && state.Items[1].Key == "B", "update keeps identity and arrival order");
state.SetDisplayed("B", true);
state.Hold("B", true);
Check(!state.Advance(TimeSpan.FromSeconds(30)).Contains("B"), "reading pauses expiry");
state.Hold("B", false);
Check(state.Advance(TimeSpan.FromSeconds(5)).Contains("B"), "visible lifetime expires after reading");
Check(!state.Advance(TimeSpan.FromMinutes(1)).Contains("A"), "pending entries do not expire before display");
state.Remove("B");
Check(state.Plan(Desktop()).Placements.Select(p => p.Key).SequenceEqual(new[] { "A", "C" }), "middle removal preserves order");

var hidden = new PopupDesktop(new(0,0,1920,1080),new(0,0,1920,1080),1,new[] { new PopupAppBar(PopupScreenEdge.Bottom,64) });
var shown = hidden with { WorkArea = new(0,0,1920,1016) };
Check(PopupStackLayout.SafeArea(hidden) == PopupStackLayout.SafeArea(shown), "auto-hide reveal does not jump or double reserve");
foreach (PopupScreenEdge edge in Enum.GetValues<PopupScreenEdge>())
{
    var desktop = hidden with { AutoHideBars = new[] { new PopupAppBar(edge,64) } };
    var safe = PopupStackLayout.SafeArea(desktop);
    Check(desktop.Monitor.Contains(safe) && (edge is PopupScreenEdge.Left or PopupScreenEdge.Right ? safe.Width == 1856 : safe.Height == 1016), "every taskbar edge reserved");
}
var crowded = new PopupStackState();
for (int i=0;i<12;i++) { crowded.Upsert($"notice{i}",360,200,false,TimeSpan.FromSeconds(4)); crowded.SetDisplayed($"notice{i}",true); }
crowded.Upsert("voice",460,276,true,null);
crowded.Upsert("stop",360,140,true,null,1);
var crowdedPlan = crowded.Plan(Desktop());
Check(crowdedPlan.Placements.Any(p=>p.Key=="stop") && crowdedPlan.Placements.Any(p=>p.Key=="voice"), "STOP and active voice have priority");
Check(crowdedPlan.Retire.Count > 0 && crowdedPlan.Placements.Any(p=>p.Key=="notice11"), "old dismissible notices retire before latest notice");
var tiny = Desktop() with { WorkArea = new(0,0,90,70) };
Check(crowded.Plan(tiny).Placements.Count==0, "unusable desktop queues instead of clipping");
var capacity = new PopupStackState();
for(int i=0;i<PopupStackState.Capacity;i++) Check(capacity.Upsert(i.ToString(),360,140,true,null), "bounded queue admission");
Check(!capacity.Upsert("overflow",360,140,true,null), "queue refuses overflow without deleting active state");
Check(capacity.Upsert("0",360,150,true,null), "existing state still updates at capacity");

foreach (double scale in new[] {1.0,1.25,1.5,2.0})
foreach (int seed in Enumerable.Range(0,1250))
{
    var random = new Random(seed);
    double x = seed%2==0 ? -2560 : 250, y = seed%3==0 ? -1440 : 70;
    double width = random.Next(640,3841), height = random.Next(480,2161);
    var desktop = new PopupDesktop(new(x,y,width,height),new(x,y,width,height),scale,
        new[] {new PopupAppBar((PopupScreenEdge)(seed%4), Math.Ceiling(64*scale))});
    var sample = new PopupStackState();
    for(int i=0;i<random.Next(1,35);i++) sample.Upsert(i.ToString(),random.Next(180,461),random.Next(60,330),i%7==0,null,i==4?1:0);
    var layout = sample.Plan(desktop).Placements;
    var area = PopupStackLayout.ContentArea(desktop);
    Check(layout.All(p=>area.Contains(p.Bounds)), $"bounds scale={scale} seed={seed}");
    Check(layout.Select(p=>p.Bounds.Right).Distinct().Count()<=1, "right alignment under scale/origin changes");
    for(int i=1;i<layout.Count;i++)
        Check(!layout[i-1].Bounds.Overlaps(layout[i].Bounds) && layout[i-1].Bounds.Bottom+Math.Ceiling(12*scale)<=layout[i].Bounds.Y, "non-overlapping scaled gaps");
    foreach (double t in new[] {0.0,1,16,40,100,160,200,500})
        Check(PopupStackLayout.Ease(t,200)>=0 && PopupStackLayout.Ease(t,200)<=1, "motion remains inside its endpoint envelope");
}
Check(PopupStackLayout.Ease(0,200)==0 && PopupStackLayout.Ease(200,200)==1, "motion settles exactly");
bool rejected=false; try { _=PopupStackLayout.SafeArea(Desktop() with {Scale=double.NaN}); } catch(ArgumentException) {rejected=true;}
Check(rejected,"invalid DPI rejected");
rejected=false; try {state.Upsert("bad",360,double.PositiveInfinity,false,null);} catch(ArgumentException) {rejected=true;}
Check(rejected,"invalid message size rejected");
Console.WriteLine($"{checks} checks passed across 5000 varied display/queue scenarios.");
