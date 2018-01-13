#! /usr/bin/env python

TODO = """
- check/implement/test thread locking (compilelock var)
"""

import copy

from mosdefutils import *
import mosdef
from MOSDEFlibc import GetMOSDEFlibc

MAXCACHESIZE = 1000

__direct_rr = ["aixremoteresolver"]

# this is a sort of pipe-through handler for all our different remote resolvers
# this is to deal with the transition period between old CANVAS design end
# NEW CANVAS design .. only mess with it if you're willing to fully test every
# remote resolver supported in CANVAS .. if you do break it and don't test *
# you owe me 50 push ups. - bas

def getremoteresolver(os, proc, version = None):
    # XXX recheck that code
    # KLUDGE:

    # if proc == x86 .. make it 'intel' .. another common mistake in MOSDEF land
    # we'll fix it here .. so we don't have to explain this to cc users :>
    # but essentially the MOSDEFLibc class will be OS_intel .. not OS_x86
    #
    # this is a little kludge .. we also had to add 'intel' to the 'X86' arch
    # translation .. because MOSDEF for assembling stuff internally uses 'X86' ;)
    # yes this gets real confusing real fast ..

    if proc.upper() in ['X86', 'I386', "I486", "I586", "I686", "I86PC", "INTEL"]:
        libc_proc   = 'intel' # libc OS_intel
        rr_proc     = 'x86' # x86osremoteresolver is the convention
    else:
        libc_proc   = proc.lower()
        rr_proc     = proc.lower()

    rros = os.lower()
    if rros == "macosx":
        rros = "osx"
    rrname = rros + "remoteresolver"

    devlog("remoteresolver","OS:%s PROC:%s VERSION:%s rrname:%s" % (os, rr_proc, version, rrname))

    # XXX: direct osremoteresolver calls ..

    if rrname in __direct_rr: # XXX
        return aixremoteresolver(libc_proc, version)
    try:
        procremoteresolver = __import__(rrname)
    except ImportError:
        print "No remoteresolver - must be CRI version"
        return None
    assert hasattr(procremoteresolver, "remoteresolver"), \
        "remoteresolver os=%s proc=%s missing me! (remoteresolver)\nmodule <%s> is:\n%s" % \
        (os, rr_proc, rrname, procremoteresolver) 

    # XXX: don't forgot about the os args .. it's a callthrough to osremoteresolver.remoteresolver
    # XXX: direct remote resolver calls are handled as above (see AIX examples) .. these need to
    # XXX: actually pass in the os argument sirs. fixed flaws introduced in revision 960

    # try specific remoteresolver
    try:
        #print "[XXX] rr: %s" % (rr_proc + rrname)
        rr = getattr(procremoteresolver, rr_proc + rrname)(os, version)
    except AttributeError:

        # try callthrough remoteresolver .. version = None by default ..
        # you HAVE to set the version from commandline .. it's easier to change
        # it there than to break * dependencies ..

        try:
            # try fallback remoteresolver
            #print "[XXX] fallback rr: %s" % rrname
            rr = getattr(procremoteresolver, rrname)()
        except AttributeError, msg:
            try:
                # try callthrough remoteresolver
                #print "[XXX] rr: remoteresolver"
                print procremoteresolver            
                rr = getattr(procremoteresolver, "remoteresolver")(os, libc_proc, version)
            except:
                print "[XXX] COULD NOT FIND CORRECT REMOTE RESOLVER .. TRY SETTING THE CORRECT VERSION"
                print "[XXX] OR CHECK OF OS_arch is VALID in MOSDEFLibc !!!"
                rr = None

            pass
    except:
        rr = None
    devlog("remoteresolver","rr returned: %s"%str(rr))
    return rr

class remoteresolver:
    
    __proc_comment_sep = {
        'X86':   "# ",
        'SPARC': "!",
        'PPC':   "!",
        'ARM':   "@",
        'MIPS':  "!",
    }

    def __init__(self, os, proc, version = None):
        #import threading
        
        self.defines={} #no defines by default
        self.fd = -1 # XXX should be set somewhere else...
        proc = proc.upper()
        self.setArch(proc)
        self.delim = self.__proc_comment_sep[self.arch]
        self.libc = GetMOSDEFlibc(os, proc, version)
        self.libc.setdefine("__%s__" % self.arch.lower(), True, force_define_with_lowercases = True)

        self.libc.initStaticFunctions()
        # XXX: re-updated in startup() with actual fd
        # XXX: also remember to update the localfunctions copy
        # XXX: in startup !!!
        # self.libc.initArchStaticFunctions(self.fd)

        self.clearfunctioncache()
        self.localcache={}
        self.clearlocalcache()

        # XXX: needs to be an actual copy .. so bouncing works ..
        # XXX: update this copy in the startup of the node post fd
        self.localfunctions = copy.deepcopy(self.libc.localfunctions)

        self.initLocalFunctions()
        return 

    def clearlocalcache(self):
        """
        You don't want to clear your local cache every time you call
        clearfunctioncache.
               
 
        """
        localcache={}
        self.localcache=localcache
        return
        
    def clearfunctioncache(self):
        devlog("mosdef", "Clearing function cache")
        #self.compilelock.acquire()
        self.functioncache = {}

        self.defines = self.libc.getdefines()
        self.vars = {}
        #self.compilelock.release()
        return 
    
    def setArch(self, proc):
        if hasattr(self, 'arch'):
            return
        archtbl = {
            #list must all be lower case - we tolower() it before we do the compare!
            'X86' : ["i386", "i486", "i586", "i686", "i86pc", "intel", 'ia64', 'x86'], # make IA64 a subclass of X86 for now ..
            #'IA64' : ['ia64'],
            'SPARC': ["sparc"],
            'PPC': ["powerpc", "ppc"],
            'ARM': ["arm", "armel"],
            'MIPS': ["mips", "mipsel"],
        }
        if archtbl.has_key(proc.upper()):
            self.arch = proc
            return
        for arch in archtbl.keys():
            if proc.lower() in archtbl[arch]:
                self.arch = arch
                return
        raise AssertionError, "proc=%s not found in archtbl: can not set self.arch" % proc
    
    def getvars(self, vars):
        d = antifloatdict(self.vars)
        d.update(vars)
        # XXX: also update self.vars? so that DSU works (and others like it)
        # because dependant on #ifndef SOCK, which checks remoteresolver.vars
        # and not these local vars (they are only local to context of compile())
        # XXX: can't do that..will mess up...think about #ifndef
        #self.vars.update(vars)
        return d
    
    def assemble(self, code):
        return mosdef.assemble(self.preprocess(code), self.arch)
    
    def compile(self, code, vars = {}, defines=None, imported = None):
        if defines==None:
            defines=self.defines
        vars = self.getvars(vars)
        unit = code + str(vars)
        if 1:
            devlog("mosdef","Looking for %s in local compile cache"%(unit))
            #for key in self.localcache:
            #    devlog("mosdef","Key: %s"%str(key))

        if unit in self.localcache:
            ret = self.localcache[unit]
            #self.compilelock.release()
            devlog("mosdef", "Found unit in local cache")
            return ret
        devlog("mosdef", "Did not find unit in local cache")
        code = self.cpreprocess(code)
        devlog("cparse", "Preprocessed c code: %s"%code)
        ret = mosdef.compile(code, self.arch, vars, defines, self, imported)
        #error checking - write this to file for output
        if not ret:
            o=file("MOSDEFCompileError.txt","wb")
            o.write(code)
            o.write("Vars= %s"%str(vars))
            o.write("Imported = %s"%str(imported))
            o.flush()
            o.close()
            
        assert ret, "mosdef.compile() for arch %s returned None\nremoteresolver: %s\n" \
            "----vars----\n%s\n----code----\n%s\n" % \
            (self.arch, self, str(vars), code)
        if len(self.localcache.keys()) > MAXCACHESIZE:
            devlog("mosdef","Clearing local cache")
            self.clearlocalcache()
        devlog("mosdef", "Adding Unit to local cache: %s"%code)
        devlog("mosdef", "Len local cache: %d"%len(self.localcache.keys()))
        self.localcache[unit] = ret #add it to our cache
        #self.compilelock.release()
        return ret
    
    def compile_to_IL(self, code, imported):
        vars = self.vars
        ##Filthy - temporary while cparse 2 in testing Rich - remove when done testing
        
        #self.use_cparse_2=True
        if hasattr(self, "use_cparse_2"):
            ret = mosdef.compile_to_IL2(code, vars, self, imported = imported)
        else:
            ret = mosdef.compile_to_IL(code, vars, self, imported = imported)
        assert ret, "mosdef.compile_to_IL() for arch %s returned None\nremoteresolver: %s\n" \
            "----vars----\n%s\n----code----\n%s\n" % \
            (self.arch, self, str(vars), code)
        return "\n" + ret + "\n"
    
    def cpreprocess(self, code):
        return mosdef.cpreprocess(code, self.vars, self.defines, self)
    
    def preprocess(self, code, delim = None):
        if delim == None:
            delim = self.delim
        return mosdef.preprocess(code, self.vars, self.defines, self, delim = delim)
    
    def initLocalFunctions(self):
        pass
    
    def getlocal(self,name,importedlocals):
        """
        Returns a function which will get included
        in the remote shellcode as a library call

        Needs to return code as IL
        """
        # 4 solaris lines
        #print "Getting local: %s"%name
        #if name in self.functioncache.keys() and self.localfunctions[name][0]!="header":
        #    return "",""
        suffix = ""
        #print self.localfunctions
        suffixtype = self.localfunctions[name][0].upper()
        suffixcode = self.localfunctions[name][1]
        if suffixtype == "IL":
            #don't assemble into IL before passing it back
            suffix = suffixcode
        elif suffixtype == "ASM":
            #change to IL before returning
            processedcode = self.preprocess(suffixcode)
            for line in processedcode.split("\n"):
                suffix += "asm %s\n" % line
        elif suffixtype == "C":
            processedcode = self.cpreprocess(suffixcode)
            #we need to change this to IL as well
            suffix = self.compile_to_IL(processedcode, importedlocals)
        elif suffixtype == "HEADER":
            suffix = self.gettypes(suffixcode)
        else:
            print "Didn't recognize suffix type: %s" % suffixtype
        self.functioncache[name] = suffix
        return "", suffix
    
    def gettypes(self, code):
        """called on header files to get the types defined within"""
        ret = mosdef.getCtypes(code, self)
        return ret

# do we want to auto-generate those class from a table OS/proc/version?

class aixremoteresolver(remoteresolver):
    def __init__(self, proc = 'powerpc', version = '5.1'):
        remoteresolver.__init__(self, 'AIX', proc, version)


if __name__== '__main__':
    aix = aixremoteresolver()
    print aix

