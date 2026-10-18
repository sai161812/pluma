using System;
using System.IO;
using System.Threading;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;

namespace PLUMA.UI.Tests
{
    internal static class Program
    {
        [STAThread]
        private static int Main()
        {
            using var log = new StreamWriter(Path.Combine(AppContext.BaseDirectory, "control-tests.txt")) { AutoFlush = true };
            Console.SetOut(log);
            Console.SetError(log);
            try
            {
                Console.WriteLine("Starting WinUI control checks");
                _ = System.Threading.Tasks.Task.Run(async () =>
                {
                    await System.Threading.Tasks.Task.Delay(TimeSpan.FromSeconds(30));
                    Console.Error.WriteLine("FAIL UI checks exceeded the 30 second timeout");
                    Environment.Exit(1);
                });
                WinRT.ComWrappersSupport.InitializeComWrappers();
                Application.Start(_ =>
                {
                    SynchronizationContext.SetSynchronizationContext(new DispatcherQueueSynchronizationContext(DispatcherQueue.GetForCurrentThread()));
                    var app = new App();
                    app.UnhandledException += (_, args) => Console.Error.WriteLine(args.Exception);
                });
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error);
                return 1;
            }
        }
    }
}
