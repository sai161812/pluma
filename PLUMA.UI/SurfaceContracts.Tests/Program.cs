using PLUMA.UI;

int checks = 0;
void Check(bool condition, string name)
{
    if (!condition) throw new InvalidOperationException(name);
    checks++;
    Console.WriteLine($"PASS {name}");
}

var feed = new LiveMessageBuffer(2);
Check(SurfaceGalleryCatalog.Items.Select(item => item.Id).SequenceEqual(Enumerable.Range(1, 26)),
    "gallery includes every planned surface exactly once in order");
Check(SurfaceGalleryCatalog.Items.All(item => !string.IsNullOrWhiteSpace(item.Name)),
    "every gallery surface has a readable label");
var timestamp = new DateTimeOffset(2026, 10, 18, 12, 0, 0, TimeSpan.Zero);
Check(feed.Entries.Count == 0, "feed starts empty");
feed.Append("  ", timestamp);
Check(feed.Entries.Count == 0, "empty events do not create rows");
feed.Append("Opened Notepad", timestamp);
Check(feed.Entries[0].Message == "Opened Notepad" && feed.Entries[0].Timestamp == timestamp,
    "executor message and timestamp are preserved exactly");
feed.Append("Stopped task", timestamp.AddSeconds(1));
feed.Append("Rollback: restored volume to 40%", timestamp.AddSeconds(2));
Check(feed.Entries.Count == 2 && feed.Entries[0].Message == "Stopped task",
    "bounded feed evicts oldest display row and preserves event order");
feed.Clear();
Check(feed.Entries.Count == 0, "clear releases displayed messages");
bool rejected = false;
try { _ = new LiveMessageBuffer(0); } catch (ArgumentOutOfRangeException) { rejected = true; }
Check(rejected, "invalid buffer capacity rejected");

var setup = new SetupChecklist();
Check(setup.Checks.Count == 5 && setup.Checks.All(check => check.State == SetupCheckState.Pending),
    "all five capability checks start unverified");
Check(!setup.MoveNext() && !setup.CanComplete, "pending dependencies block navigation and completion");
foreach (var check in setup.Checks.Where(check => check.Step == 0))
    setup.Update(check.Id, SetupCheckState.Passed, "Host verified");
Check(setup.MoveNext() && setup.CurrentStep == 1, "verified dependencies allow input checks");
setup.Update(SetupCheckId.Microphone, SetupCheckState.Failed, "Access denied");
setup.Update(SetupCheckId.Hotkeys, SetupCheckState.Passed, "Registered");
Check(!setup.MoveNext() && !setup.IsReady, "denied microphone access prevents completion");
setup.Update(SetupCheckId.Microphone, SetupCheckState.Passed, "Access granted");
Check(setup.MoveNext() && setup.CanComplete, "all capabilities verified before Continue");
setup.Update(SetupCheckId.LocalModel, SetupCheckState.Failed, "File removed");
Check(!setup.CanComplete, "later capability failure revokes Continue");
setup.MoveBack();
Check(setup.CurrentStep == 1 && !setup.MoveNext(), "earlier failed dependency also blocks advancing again");
setup.Reset();
Check(setup.CurrentStep == 0 && setup.Checks.All(check => check.State == SetupCheckState.Pending && check.Detail == ""),
    "recheck invalidates previous evidence and details");
rejected = false;
try { setup.Update(SetupCheckId.Hotkeys, (SetupCheckState)99, ""); }
catch (ArgumentOutOfRangeException) { rejected = true; }
Check(rejected && !setup.IsReady, "invalid check state rejected without enabling Continue");

Console.WriteLine($"{checks} checks passed.");
