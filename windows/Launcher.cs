using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("WaxTranslate")]
[assembly: AssemblyProduct("WaxTranslate")]

internal static class Launcher
{
    [STAThread]
    private static int Main(string[] args)
    {
        bool background = args.Length == 1 && args[0] == "--background";
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "runtime", "pythonw.exe");
        string script = Path.Combine(root, "windows", "app.py");
        try
        {
            string arguments = "\"" + script + "\"" + (background ? " --background" : "");
            Process.Start(new ProcessStartInfo(python, arguments) {
                UseShellExecute = false, WorkingDirectory = root
            });
            return 0;
        }
        catch (Exception error)
        {
            if (!background)
                MessageBox.Show("请完整解压便携包后再启动。\n" + error.Message, "WaxTranslate");
            return 1;
        }
    }
}
