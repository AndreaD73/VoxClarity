# Modern Windows folder picker (Explorer-style dialog with address bar, FOS_PICKFOLDERS).
# Prints the chosen folder in UTF-8, nothing if cancelled.
param([string]$Start = "", [string]$Title = "Scegli la cartella")
$code = @"
using System;
using System.Runtime.InteropServices;
public static class FolderPick {
    [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] class FileOpenDialogCo { }
    [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IFileOpenDialog {
        [PreserveSig] int Show(IntPtr owner);
        void SetFileTypes(); void SetFileTypeIndex(); void GetFileTypeIndex(); void Advise(); void Unadvise();
        void SetOptions(uint fos); void GetOptions(out uint fos);
        void SetDefaultFolder(IShellItem si); void SetFolder(IShellItem si);
        void GetFolder(); void GetCurrentSelection(); void SetFileName(); void GetFileName();
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel(); void SetFileNameLabel();
        void GetResult(out IShellItem si);
    }
    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItem {
        void BindToHandler(); void GetParent();
        void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
    }
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateItemFromParsingName(string path, IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid riid, out IShellItem item);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    public static string Pick(string start, string title) {
        var d = (IFileOpenDialog)new FileOpenDialogCo();
        d.SetOptions(0x20 | 0x40 | 0x800);           // PICKFOLDERS | FORCEFILESYSTEM | PATHMUSTEXIST
        d.SetTitle(title);
        if (!string.IsNullOrEmpty(start) && System.IO.Directory.Exists(start)) {
            IShellItem si; SHCreateItemFromParsingName(start, IntPtr.Zero, typeof(IShellItem).GUID, out si);
            d.SetFolder(si);
        }
        if (d.Show(GetForegroundWindow()) != 0) return "";
        IShellItem r; d.GetResult(out r);
        string path; r.GetDisplayName(0x80058000, out path);   // SIGDN_FILESYSPATH
        return path;
    }
}
"@
Add-Type -TypeDefinition $code
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Write-Output ([FolderPick]::Pick($Start, $Title))
