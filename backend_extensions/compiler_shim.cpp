// SPDX-License-Identifier: GPL-3.0-only
// Windows launcher for the pinned, source-built PLC Workbench compiler.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string>
#include <vector>
#include <iostream>

static std::wstring path_file(const std::wstring& path) {
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
    if(file==INVALID_HANDLE_VALUE)throw 1;
    char bytes[32768];DWORD size=0;
    bool okay=ReadFile(file,bytes,sizeof(bytes),&size,nullptr);CloseHandle(file);
    if(!okay || size==sizeof(bytes))throw 2;
    int count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,bytes,size,nullptr,0);
    if(count<=0)throw 3;
    std::wstring result(count,L'\0');
    MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,bytes,size,result.data(),count);
    while(!result.empty() && (result.back()==L'\r'||result.back()==L'\n'))result.pop_back();
    return result;
}
static std::wstring quote(const std::wstring& arg) {
    std::wstring out=L"\"";std::size_t slashes=0;
    for(wchar_t ch:arg){
        if(ch==L'\\'){++slashes;continue;}
        if(ch==L'\"'){out.append(2*slashes+1,L'\\');out+=ch;}
        else{out.append(slashes,L'\\');out+=ch;}
        slashes=0;
    }
    out.append(2*slashes,L'\\');out+=L'\"';return out;
}
int wmain(int argc,wchar_t** argv) {
    try{
        if(argc==2 && std::wstring(argv[1])==L"--version"){
            std::cout<<"STruC++ 0.7.0 + PLC-R4 (fcccfbdf)"<<std::endl;return 0;
        }
        wchar_t module[32768];DWORD size=GetModuleFileNameW(nullptr,module,32768);
        if(size==0 || size==32768)return 100;
        std::wstring home(module,size);home=home.substr(0,home.find_last_of(L"\\/")+1);
        std::wstring node=path_file(home+L"node-path.txt"),cli=path_file(home+L"cli-path.txt");
        std::wstring command=quote(node)+L" "+quote(cli);
        for(int i=1;i<argc;++i)command+=L" "+quote(argv[i]);
        HANDLE job=CreateJobObjectW(nullptr,nullptr);if(!job)return 101;
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if(!SetInformationJobObject(job,JobObjectExtendedLimitInformation,&limits,sizeof(limits))){CloseHandle(job);return 102;}
        STARTUPINFOW start{};start.cb=sizeof(start);start.dwFlags=STARTF_USESTDHANDLES;
        start.hStdInput=GetStdHandle(STD_INPUT_HANDLE);start.hStdOutput=GetStdHandle(STD_OUTPUT_HANDLE);start.hStdError=GetStdHandle(STD_ERROR_HANDLE);
        PROCESS_INFORMATION child{};
        if(!CreateProcessW(node.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_SUSPENDED,nullptr,nullptr,&start,&child)){CloseHandle(job);return 103;}
        if(!AssignProcessToJobObject(job,child.hProcess)){
            TerminateProcess(child.hProcess,104);CloseHandle(child.hThread);CloseHandle(child.hProcess);CloseHandle(job);return 104;
        }
        ResumeThread(child.hThread);CloseHandle(child.hThread);WaitForSingleObject(child.hProcess,INFINITE);
        DWORD code=0;GetExitCodeProcess(child.hProcess,&code);CloseHandle(child.hProcess);CloseHandle(job);return static_cast<int>(code);
    }catch(...){std::cerr<<"PLC-R4 compiler installation is incomplete"<<std::endl;return 105;}
}
