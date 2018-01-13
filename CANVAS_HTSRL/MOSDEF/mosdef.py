#! /usr/bin/env python

"""
MOSDEF (pronounced mos' def!) is a compiler from C->shellcode
Copyright Dave Aitel 2003
"""

import sys, types
import atandtscan
import atandtparse
import cparse
import cpp

USE_CPARSE2=True
import cparse2, yacc

if "." not in sys.path: sys.path.append(".")

from ast import AST

from mosdefutils import *

_debug = False

def dumpfile(bool, data, filename = "out", mode = "w", rand = False):
    global _debug
    if _debug or bool:
        if rand:
            import random
            filename += ".%d" % random.randint(1, sys.maxint - 1)
        f = open(filename, mode)
        f.write(data)
        f.close()
    return 

class MOSDEFCompiler:
    def __init__(self):
        pass
    
    def setParser(self,parser):
        self.parser=parser
    
    def setScanner(self,scanner):
        self.scanner=scanner
    
    def compile(self,data):
        """
        takes in a string of data, compiles it to object code, returns that object code or
        an error message
        """
        tokens=self.scanner(data)
        #if debugging...
        #print tokens
        try:
            parsed=self.parser(tokens)
        except SystemExit:
            print "Failed to parse file: %s"%data
        return 0,None,"yo"


def getremoteresolver(os, proc, version = None):
    #we avoid a circular reference here
    from MOSDEF.remoteresolver import getremoteresolver
    return getremoteresolver(os, proc, version)

def cpreprocess(cdata, vars, defines, remoteresolver):
    return cpp.cpreprocess(cdata, vars, defines, remoteresolver)

def preprocess(data,vars, defines, remoteresolver, delim = None):
    return cpp.preprocess(data, vars, defines, remoteresolver, delim = delim)

def compile_to_IL(data, vars, remoteresolver, imported, debug=0):
    if USE_CPARSE2:
	return compile_to_IL2(data, vars, remoteresolver, imported, debug=0)
	
    #print "<<<<<<<<<<<<<<<<<<<<<<< USING CPARSE 1 uiuFOR COMPILATION of : >>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    if hasattr(remoteresolver, "use_cparse_2"):
	print "*_*_**_*_**_*_**_*_**_*_**_*_**_*_**_*_**_*_**_*_**_*_**_*_**_*_**_*_**_*_*"
	il=compile_to_IL2(data, vars, remoteresolver, imported, debug=debug)
	
    assert type(remoteresolver) == types.InstanceType
    devlog("cparse", "compile_to_IL data: %s"%data)
    dumpfile(debug, data, "out.E", rand = True)
    dumpfile(debug, arraydump(vars), "out.c_vars")
    tokens=cparse.scan(data)
    devlog("cparse", "Correctly parsed into tokens")
    myparser=cparse.cparser(AST,'file_input')
    #Why would we need this?
    #myparser.setRemoteResolver(remoteresolver)
    tree=myparser.parse(tokens)
    generator=cparse.ilgenerate(tree,vars,remoteresolver=remoteresolver,imported=imported)
    il=generator.get() #now we have intermediate language
    return il

##New function that uses cparse2 not cparse
def compile_to_IL2(data, vars, remoteresolver, imported, debug=0):
    #print "<<<<<<<<<<<<<<<<<<<<<<< USING CPARSE 2 FOR COMPILATION of : >>>>>>>>>>>>>>>>>>>>>>>>>>>>"
    assert type(remoteresolver) == types.InstanceType
    #devlog("cparse2", "compile_to_IL data: %s"%data)
    dumpfile(debug, data, "out.E", rand = True)
    dumpfile(debug, arraydump(vars), "out.c_vars")
    
    ##Initialise our lexer logic and lex, as well as our parser logic
    parser=cparse2.CParse2(remoteresolver=remoteresolver, vars=vars, imported=imported)
    
    yaccer=yacc.yacc(module=parser,debug=0,write_tables=1,method="SLR",tabmodule=remoteresolver.parse_table_name)

    try:
	ret_IL=yaccer.parse(data, lexer=parser.lexer)
    except Exception, err:
	raise
    
    il = "".join(parser.value)
    return il

#we optimize slightly here by pre-importing every architecture. This
#uses memory, but avoids an import on a per-CPU basis later on
__supported_proc = ["X86", "SPARC", "PPC"] #, "ARM", "MIPS"
__proc_dict = {}
for il in __supported_proc:
    try:
        il2proc = __import__('il2%s' % il.lower())
        __proc_dict[il]=il2proc
    except ImportError:
        pass
        #print "CRI Version on %s"%il
    
def compile(data, arch, vars, defines, remoteresolver, imported=None, debug=0):
    """
    imported functions don't get GETPC compiled into them
    """
    assert type(remoteresolver) == types.InstanceType
    #debug=1 #for debugging use only
    dumpfile(debug, data, "out.c", rand = True)
    data = preprocess(data, vars, defines, remoteresolver, delim = "//")
    dumpfile(debug, arraydump(defines), "out.c_defines", rand = True)
    
    ##Rich filthy, remove after testing - cparse_version stuff TODO -----------------------
    if hasattr(remoteresolver, "use_cparse_2"):
	il=compile_to_IL2(data, vars, remoteresolver, imported, debug=debug)
    else:
	il=compile_to_IL(data, vars, remoteresolver, imported, debug=debug)
    
    dumpfile(debug, il, "out.il")
    #print "IL=\n%s"%il
    arch=arch.upper()
    if arch in __proc_dict.keys():
        il2proc=__proc_dict[arch]
        asm = il2proc.generate(il)
        dumpfile(debug, asm, "out.s")
    else:
        print "Uh, mosdef.compile doesn't speak %s"%arch
        # FIXME good return value ?
        return None
    
    #print "ASM=%s"%asm
    bytecodes=assemble(asm,arch)
    #convert2asm=cparse.getil2asm(arch)
    
    return bytecodes

def getCtypes(data,remoteresolver):
    assert type(remoteresolver) == types.InstanceType
    data = preprocess(data, {}, {}, remoteresolver, delim = "//")
    tokens=cparse.scan(data)
    myparser=cparse.cparser(AST,'file_input')
    #Why would we need this?
    #myparser.setRemoteResolver(remoteresolver)
    tree=myparser.parse(tokens)
    # XXX until all *remoteresolver use remoteresolver.py
    if not hasattr(remoteresolver, 'vars'):
        print "remoteresolver %s misses 'vars' member..." % remoteresolver
        vars = {} # will probably crash later
    else:
        vars = remoteresolver.vars
    generator=cparse.ilgenerate(tree,vars,remoteresolver=remoteresolver,imported=None)
    rettypes=generator.gettypes()
    return rettypes

def assemble(data,arch):
    """
    assembles a given block of data into bytecodes
    Just a callthrough to assembleEx
    """
    #debug each and every shellcode we compile...slower
    dumpfile(0, data, "temp.s", "wb")
    return assembleEx(data,arch)[0]

# XXX TODO what a mess...
import x86parse 
def assembleEx(data,arch):
    devlog("mosdef", "Assembling with arch %s"%arch)
    if data in ["", None]:
        devlog("mosdef", "assembling nothing!")
        return (None, None)
    
    if arch.upper()=="X86":
        #write out every assembled file...
        #file("mcode.s","w").write(data)
        if 1:
            devlog("mosdef", "Using new assembler")
            data=x86parse.assemble_x86(data)
        else:
            #old assembler is not compatible with 
            #solaris x86 shellcode because we use CPUID
            #and a lot of other stuff it can't handle
            devlog("mosdef","Using old assembler")
            data=atandtparse.atandtpreprocess(data)
            #print data
            tokens=atandtscan.scan(data)
            #print tokens
            #print "Getting tree"
            try:
                tree=atandtparse.parse(tokens)
            except:
                import traceback
                traceback.print_exc(file=sys.stdout)
                print "Syntax error in: %s"%data
                #change these numbers for sanity when you find
                #the line number...
                lines=data.split("\n")[68:75]
                print "Lines: %s"%("\n".join(lines))
                name="parserbug_assembly.txt"
                print "Writing code that generated exception to %s"%name
                o=file(name,"wb")
                o.write(data)
                o.close()
                return (None,None)
            try:
                #print "Getting generation"
                x=atandtparse.x86generate(tree)
            except:
                import traceback
                traceback.print_exc()
                print "syntax error:"
                print data
                return (None, None)
            #print "Done assembling"
            return (x.value,x.metadata)
        return (data, None)
    
    
    elif arch.upper() in ["SPARC", "PPC", "ARM"]:
        procparse = __import__('%sparse' % arch.lower())
        parser,yaccer=procparse.getparser()
        lexer=parser.lexer
        #print "pass 1" 
        yaccer.parse(data,lexer=lexer,debug=0)
        #print "1: %s"%parser.labelinfo
        parser2,yaccer2=procparse.getparser(runpass=2)
        parser2.labelinfo=parser.labelinfo #saved off from runpass 1
        #print "2: %s %s"%(parser2.labelinfo,parser2.runpass)
        lexer2=parser2.lexer
        #print "pass 2"
        yaccer2.parse(data,lexer=lexer2,debug=0)
        data="".join(parser2.value)
        #print hexprint(data)
        return (data, None) #no metadata?
    
    print "Unknown arch: %s"%arch
    return (None,None)

def usage():
    print "Usage: "+sys.argv[0]+" -f filename [-a asmtoassemble] [-s %s]" % "/".join(__supported_proc)
    sys.exit(1)

def test():
    """
    This little function is used to regression test issue that MOSDEF 
    has had in the past, and make sure they are fixed
    """
    ret=1
    correctList=[]
    correctList.append(["movb %cl, %al","X86",["\x8A\xC1"]])
    correctList.append(["movb %al, %al","X86",["\x88\xc0","\x8a\xc0"]])
    correctList.append(["movb %al, %bl","X86",["\x88\xc3","\x8a\xd8"]])
    correctList.append(["movb %al, %cl","X86",["\x88\xc1","\x8a\xc8"]])
    correctList.append(["movb %al, %dl","X86",["\x88\xc2","\x8a\xd0"]])
    correctList.append(["ror $13, %edi","X86",["\xc1\xcf\x0d"]])
    correctList.append(["popl %fs:(%edx)","X86",["\x64\x8f\x02"]])
    correctList.append(["addl $-1234, %esp","X86",["\x81\xc4\x2e\xfb\xff\xff"]])
    correctList.append(["and %edx, %eax","X86",["\x21\xd0","\x21\xd2"]])
    correctList.append(["pushl $201","X86",["\x68\xc9\x00\x00\x00"]])
    correctList.append(["pushl $1","X86",["\x6a\x01"]])
    correctList.append(["pushl $-1","X86",["\x6a\xff"]])
    correctList.append(["geteip:\nmovl %eax, fun-geteip(%ebx)\nfun:\n","X86",["\x89\x43\x06\x90\x90\x90"]])
    correctList.append(["geteip:\nmovl $0x01020304, fun-geteip(%ebx)\nfun:\n","X86"
                        ,["\xc7\x43\x0a\x04\x03\x02\x01\x90\x90\x90"]])
    correctList.append(["geteip:\ncall geteip\n","X86",["\xe8\xfb\xff\xff\xff"]]) 
    correctList.append(["call geteip\ngeteip:\n","X86",["\xe8\x00\x00\x00\x00"]])
    correctList.append(["geteip:\ncall 250(%ebx)\nfun:\n","X86",["\xff\x13"]])
    correctList.append(["geteip:\nmovl $4, go-geteip(%ebx)\ngo:\n","X86",["\x01\x02"]])
    
    
    for example in correctList:
        result=assemble(example[0],example[1])
        print "%s =         %s"%(example[0],hexprint(result))
        if result not in example[2]:
            print "Error assembling %s"%example[0]
            print "Possibles: %s"%hexprint(example[2][0])
            ret=0
    if ret:
        print "All tests passed!"
    return ret
    

#import curses.ascii

def isprint(str):
    for i in str:
        if not ord(i) in range(0x20,0x7f):
            return 0
    return 1

def strisprint(str):
    for i in str:
        if not isprint(i):
            return 0
    return 1


if __name__=="__main__":
    import getopt
    if 1:
        output=assemble("mov %eax, 0x8(%esp,4)","X86")
    try:
        (opts,args)=getopt.getopt(sys.argv[1:],"f:Ta:s:")
    except getopt.GetoptError:
        print "Wrong arguments"
        usage()
    
    filename=""
    dofile=0
    asm=""
    arch="X86"
    for o,a in opts:
        if o in ["-f"]:
            dofile=1
            filename=a
        if o in ["-T"]:
            test()
            sys.exit(1)
        if o in ["-a"]:
            print "Setting asm to %s"%a
            asm=a
        if o in ["-s"]:
            arch=a
    if dofile and filename=="":
        usage()
    
    if dofile:
        mycompiler=MOSDEFCompiler()
        data=open(filename).read()
        print "Assembling (%s):\n%s"%(arch,data[:50])
        output=assemble(data,arch)
        print "Length: %d"%len(output)
        #print "output=%s"%hexprint(output)
        line = 0
        for c in output:
            sys.stdout.write("%02x "%ord(c))
            line += 1
            if line == 4:
                sys.stdout.write("\n")
                line = 0
        dumpfile(True, output, "asm.out", "wb")
    if asm!="":
        result=assemble(asm,arch)
        print "Result=%s"%hexprint(result)
        print "Isprint(result)=%d"%strisprint(result)

