#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <wchar.h>
#include <stdio.h>
static int fail(const wchar_t *message){MessageBoxW(NULL,message,L"BrickLabo",MB_OK|MB_ICONERROR);return 1;}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR arguments,int show){
    (void)instance;(void)previous;(void)show;
    wchar_t root[32768],python[32768],bootstrap[32768],temporary[32768],command[32768];
    DWORD length=GetModuleFileNameW(NULL,root,32768);
    if(!length||length>=32768)return fail(L"Chemin du logiciel trop long. / Application path too long.");
    wchar_t *slash=wcsrchr(root,L'\\');if(!slash)return fail(L"Dossier introuvable. / Folder not found.");*slash=L'\0';
    if(wcslen(root)>15000)return fail(L"Place BrickLabo dans un chemin plus court. / Move BrickLabo to a shorter path.");
    swprintf(python,32768,L"%ls\\app\\pythonw.exe",root);swprintf(bootstrap,32768,L"%ls\\app\\bootstrap.py",root);swprintf(temporary,32768,L"%ls\\Donnees\\temp",root);
    SetEnvironmentVariableW(L"BRICKLABO_ROOT",root);SetEnvironmentVariableW(L"TEMP",temporary);SetEnvironmentVariableW(L"TMP",temporary);SetEnvironmentVariableW(L"TMPDIR",temporary);
    int count=_snwprintf(command,32768,L"\"%ls\" -B \"%ls\" %ls",python,bootstrap,arguments);
    if(count<0||count>=32768)return fail(L"Commande trop longue. / Command line too long.");
    STARTUPINFOW startup={0};startup.cb=sizeof(startup);PROCESS_INFORMATION process={0};
    if(!CreateProcessW(python,command,NULL,NULL,FALSE,0,NULL,root,&startup,&process)){
        wchar_t message[1024];swprintf(message,1024,L"Impossible de lancer BrickLabo (erreur %lu).\nExtrais l'archive complete et conserve app et ressources. Essaie un chemin plus court.\n\nUnable to start BrickLabo: extract the entire archive, retain all folders and try a shorter path.",GetLastError());return fail(message);
    }
    CloseHandle(process.hThread);WaitForSingleObject(process.hProcess,INFINITE);DWORD status=1;GetExitCodeProcess(process.hProcess,&status);CloseHandle(process.hProcess);return (int)status;
}
