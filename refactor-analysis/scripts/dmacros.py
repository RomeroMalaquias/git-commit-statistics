#!/usr/bin/python
# -*- coding: utf-8 -*-

# modules from the std-library
import os
import re
import sys
from optparse import OptionParser, OptionGroup

# external libs
# python-lxml module
try:
    from lxml import etree
except ImportError:
    print("python-lxml module not found! (python-lxml)")
    print("see http://codespeak.net/lxml/")
    print("programm terminating ...!")
    sys.exit(-1)

__cppnscpp = 'http://www.sdml.info/srcML/cpp'
__cpprens = re.compile('{(.+)}(.+)')


def returnFileNames(folder, extfilt = ['.xml']):
    '''This function returns all files of the input folder <folder>
    and its subfolders.'''
    filesfound = list()

    if os.path.isdir(folder):
        wqueue = [os.path.abspath(folder)]

        while wqueue:
            currentfolder = wqueue[0]
            wqueue = wqueue[1:]
            foldercontent = os.listdir(currentfolder)
            tmpfiles = filter(lambda n: os.path.isfile(
                    os.path.join(currentfolder, n)), foldercontent)
            tmpfiles = filter(lambda n: os.path.splitext(n)[1] in extfilt,
                    tmpfiles)
            tmpfiles = map(lambda n: os.path.join(currentfolder, n),
                    tmpfiles)
            filesfound += tmpfiles
            tmpfolders = filter(lambda n: os.path.isdir(
                    os.path.join(currentfolder, n)), foldercontent)
            tmpfolders = map(lambda n: os.path.join(currentfolder, n),
                    tmpfolders)
            wqueue += tmpfolders

    return filesfound


class DisciplinedAnnotations:
    ##################################################
    # constants:
    __cppnscpp = 'http://www.sdml.info/srcML/cpp'
    __cppnsdef = 'http://www.sdml.info/srcML/src'
    __cpprens = re.compile('{(.+)}(.+)')
    __conditionals = ['if', 'ifdef', 'ifndef', 'else', 'elif', 'endif']
    __conditions   = ['if', 'ifdef', 'ifndef']
    ##################################################	
    

    def __init__(self, inputDir):
	self.results = []
        oparser = OptionParser()
        oparser.add_option('-d', '--dir', dest='dir',
                help='input directory (mandatory)')
        oparser.add_option('-l', '--log', dest='log',
                default=False, help='log to stdout (default=True)')
        oparser.add_option('-c', '--check', dest='check', type='int',
                default=1, help='pattern check (default=1)')
        oparser.add_option('-v', '--verbose', dest='verbose', type='int',
                default=0, help='verbose output (default=0)')
        oparser.add_option('-a', '--all', dest='all', type='int',
                default=0, help='check all patterns (default=0)')
        groupc = OptionGroup(oparser, 'Check',
                'This option allows to set the patterns, that are '
                'checked during the program run: '
                '(1) check top level siblings (compilation unit) '
                '(2) check sibling (excludes check top level siblings; NOT CLASSIFIED) '
                '(4) check if-then enframement (wrapper) '
                '(8) check case enframement (conditional) '
                '(16) check else-if enframement (conditional) '
                '(32) check param/argument enframement (parameter) '
                '(64) check expression enframement (expression) '
                '(128) check else enframement (NOT CLASSIFIED) '
        )
        oparser.add_option_group(groupc)
        groupr = OptionGroup(oparser, 'Result',
                'This program counts the number of the disciplined '
                'cpp usage in software projects. To this end, it '
                'checks xml representations of header and source '
                'files and returns the number of disciplined ifdefs '
                'in those. Disciplined annotations are: '
        )
        oparser.add_option_group(groupr)
        (self.opts, self.args) = oparser.parse_args()

        if not self.opts.dir:
	    if not inputDir:
                oparser.print_help()
                sys.exit(-1)
	    else:
		self.opts.dir = inputDir

        self.overallblocks = 0
        self.disciplined = 0
        self.undisciplinedknown = 0
        self.undisciplinedunknown = 0
        self.compilationunit = 0
        self.functiontype = 0
        self.siblings = 0
        self.wrapperif = 0
        self.wrapperfor = 0
        self.wrapperwhile = 0
        self.conditionalcase = 0
        self.conditionalelif = 0
        self.parameter = 0
        self.expression = 0
        self.loc = 0
        return self.checkFiles()

    def __getIfdefAnnotations__(self, root):
        '''This method returns all nodes of the xml which are ifdef
        annotations in the source code.'''
        treeifdefs = list()

        for _, elem in etree.iterwalk(root):
            ns, tag = DisciplinedAnnotations.__cpprens.match(elem.tag).\
                    groups()

            if ns == DisciplinedAnnotations.__cppnscpp \
                    and tag in DisciplinedAnnotations.__conditionals:
                treeifdefs.append(elem)
                
        return treeifdefs


    def __createListFromTreeifdefs__(self, treeifdefs):
        '''This method returns a list representation for the input treeifdefs
        (xml-objects). Corresponding #ifdef elements are in one sublist.'''

        if not treeifdefs: return []

        listifdefs = list()
        workerlist = list()
        for nifdef in treeifdefs:
            tag = nifdef.tag.split('}')[1]
            if tag in ['if', 'ifdef', 'ifndef']:
                workerlist.append(list())
                workerlist[-1].append(nifdef)
            elif tag in ['elif', 'else']:
                workerlist[-1].append(nifdef)
            elif tag in ['endif']:
                if not workerlist:
                    return -1
                workerlist[-1].append(nifdef)
                last = workerlist[-1]
                getpairs = zip(last,last[1:])
                map(lambda i: listifdefs.append(list(i)), getpairs)
                workerlist = workerlist[:-1]
            else:
                print('[ERROR] ill-formed tag (%s) occured in line (%4s).' % (tag, nifdef.sourceline))

        if workerlist:
            return -2

        return listifdefs

    def __filterConditionalPreprocessorDirectives(self, listifdefs):
        '''This method filters out all ifdef-endif pairs that annotate only preprocessor directives.'''
        # iterate annotated blocks by determining all siblings of the #ifdef and filter out preprocessor
        # annotated elements
        resultlist = filter(lambda (ifdef, endif): ifdef.getnext() != endif, listifdefs)
        #print('[INFO] before after: %s <-> %s' % (str(len(listifdefs)), str(len(resultlist))))
        return resultlist


    PATTLS = 0 # 1 << 0 => 1
    def __checkStrictTLSFDPattern__(self, listifdefs):
        '''like sibling pattern, but only top level and statement elements are
        considered disciplined'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            nodeifdef = listcorifdef[0]
            nodeifdefsibs = [sib for sib in nodeifdef.itersiblings()]

            error=0
            for corifdef in listcorifdef[1:]:
                if not corifdef in nodeifdefsibs:
                    error=1

            if error==0:
                parenttag = self.__getParentTag__(nodeifdef)
                if not parenttag in ['block','public']:
                    error=1
            if error==1:
                listundisciplinedunknown.append(listcorifdef)
            else:
                listundisciplinedknown.append(listcorifdef)

        return (listundisciplinedknown, listundisciplinedunknown)


    def __checkStrictTLSCUPattern__(self, listifdefs):
        '''This method checks all patterns, if they occur right under the root element
        of the grammer, here unit.'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            nodeifdef = listcorifdef[0]
            nodeifdefsibs = [sib for sib in nodeifdef.itersiblings()]

            error=0
            for corifdef in listcorifdef[1:]:
                if not corifdef in nodeifdefsibs:
                    error=1

            if error==0:
                parenttag = self.__getParentTag__(nodeifdef)
                if not parenttag in ['unit']:
                    error=1
            if error==1:
                listundisciplinedunknown.append(listcorifdef)
            else:
                listundisciplinedknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)


    def __checkStrictPattern__(self, listifdefs):
        '''This pattern checks the annotation of functions, where the XML markup
        of src2srcml is ill-formed. TODO might be fixed in future versions of
        src2srcml. Example is:
        void foo(k)
        int k;
        {
        // some lines of code
        }
        '''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            if len(listcorifdef) != 2:
                listundisciplinedunknown.append(listcorifdef)
                continue

            nodeifdef = listcorifdef[0]
            nodeendif = listcorifdef[1]
            func = nodeendif.getparent()

            if func != None and func.tag.split('}')[1] == 'function':
                nodefuncsibs = [sib for sib in func.itersiblings(preceding=True)]
                if nodeifdef == nodefuncsibs[0]:
                    if self.opts.verbose:
                        print('[INFO] ill-formed compilation unit pattern occured in line (%4s).' % nodeifdef.sourceline)
                    listundisciplinedknown.append(listcorifdef)
                    continue

            listundisciplinedunknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)


    PATSIB = 1 # 1 << 1 => 2
    def __checkSiblingPattern__(self, listifdefs):
        '''This method returns a tuple with (listdisciplined,
        listundisciplined) #ifdef elements. The pattern works on the basis
        of the sibling pattern. If the xml elements of #if-#elif-#else-#endif
        are siblings, we determine them as disciplined.'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            nodeifdef = listcorifdef[0]
            nodeifdefsibs = [sib for sib in nodeifdef.itersiblings()]

            error=0;
            for corifdef in listcorifdef[1:]:
                if not corifdef in nodeifdefsibs:
                    error=1
            if error==1:
                listundisciplinedunknown.append(listcorifdef)
            else:
                listundisciplinedknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)


    def __getParentTag__(self, tag):
        parent = tag.getparent()
        return parent.tag.split('}')[1]


    PATIFTHEN = 2 # 1 << 2 => 4
    def __checkIfThenPattern__(self, listifdefs):
        '''This method returns a tuple with (listdisciplined,
        listundisciplined) #ifdef elements. The pattern matches the following
        situation. The if-then in C is enframed by #if-#endif. The else part of
        the if-then in C is not enframed. The sibling pattern does not work here
        since the annatation cannot work properly here.'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            if len(listcorifdef) != 2:
                listundisciplinedunknown.append(listcorifdef)
                continue

            # check that the endif is the first child of its parent and the parent
            # is an else
            ifdef = listcorifdef[0]
            ifdefsibs = [sib for sib in ifdef.itersiblings()]

            # first sibling of starting ifdef must be an if
            if len(ifdefsibs) == 0 or ifdefsibs[0].tag.split('}')[1] != 'if':
                listundisciplinedunknown.append(listcorifdef)
                continue

            # parent of endif must be either an else or an then (if)
            endif = listcorifdef[1]
            poselse = endif.getparent()
            poselsetag = poselse.tag.split('}')[1]
            if poselsetag in ['else', 'then']:
                if self.opts.verbose:
                    print('[INFO] if-then pattern occured in line (%4s).' % poselse.sourceline)
                listundisciplinedknown.append(listcorifdef)
            else:
                listundisciplinedunknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)

    #TODO
    def __checkForWrapperPattern__(self, listifdefs):
        '''This method returns a tuple with (listdisciplined,
        listundisciplined) #ifdef elements. The pattern matches the following
        situation. The for in C is enframed by #if-#endif.'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            if len(listcorifdef) != 2:
                listundisciplinedunknown.append(listcorifdef)
                continue

            # check that the endif is the first child of its parent and the parent
            # is an else
            ifdef = listcorifdef[0]
            ifdefsibs = [sib for sib in ifdef.itersiblings()]

            # first sibling of starting ifdef must be an for
            if len(ifdefsibs) == 0 or ifdefsibs[0].tag.split('}')[1] != 'for':
                listundisciplinedunknown.append(listcorifdef)
                continue

            # parent of endif must be either an else or an then (if)
            endif = listcorifdef[1]
            poselse = endif.getparent()
            poselsetag = poselse.tag.split('}')[1]
            if poselsetag in ['else', 'then']:
                if self.opts.verbose:
                    print('[INFO] if-then pattern occured in line (%4s).' % poselse.sourceline)
                listundisciplinedknown.append(listcorifdef)
            else:
                listundisciplinedunknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)


    PATCASE = 3 # 1 << 3 => 8
    def __checkCasePattern__(self, listifdefs):
        '''The method checks the case-block pattern; the #ifdef enframes a case block
        of a switch case.'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            # pattern works only for #if-#endif combinations
            if len(listcorifdef) > 2:
                listundisciplinedunknown.append(listcorifdef)
                continue

            # get endif and check whether parent is a case
            nodeendif = listcorifdef[-1]
            parenttag = self.__getParentTag__(nodeendif)
            if parenttag in ['case']:
                if self.opts.verbose:
                    print('[INFO] case pattern occured in line (%4s).' % nodeendif.sourceline)
                listundisciplinedknown.append(listcorifdef)
            else:
                listundisciplinedunknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)

    PATELSEIF = 4 # 1 << 4 => 16
    def __checkElseIfPattern__(self, listifdefs):
        '''The method check the elseif-block pattern; the #ifdef enframes an elseif
        block in an if-then-else.'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            # pattern works only for #if-#endif combinations
            if len(listcorifdef) > 2:
                listundisciplinedunknown.append(listcorifdef)
                continue

            # get the endif
            # endif parent -> then
            # then parent -> if
            # if parent -> else
            # else parent -> #ifdef
            nodeendif = listcorifdef[-1]
            thensib = nodeendif.getprevious()
            if thensib == None:
                listundisciplinedunknown.append(listcorifdef)
                continue
            if thensib.tag.split('}')[1] not in ['then']:
                listundisciplinedunknown.append(listcorifdef)
                continue
            ifparent = thensib.getparent()
            if ifparent.tag.split('}')[1] not in ['if']:
                listundisciplinedunknown.append(listcorifdef)
                continue
            elseparent = ifparent.getparent()
            if elseparent.tag.split('}')[1] not in ['else']:
                listundisciplinedunknown.append(listcorifdef)
                continue
            ifdefsib = elseparent.getprevious()

            if ifdefsib != listcorifdef[0]:
                if self.opts.verbose:
                    print('[INFO] else-if pattern occured in line (%4s).' % ifdefsib.sourceline)
                listundisciplinedunknown.append(listcorifdef)
            else:
                listundisciplinedknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)

    PATPARAM = 5 # 1 << 5 => 32
    def __checkParameter__(self, listifdefs):
        '''The method checks whether an #ifdef enframes a parameter of a function;
        includes function definitions and function calls.'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            # pattern works only for #if-#endif combinations
            if len(listcorifdef) > 2:
                listundisciplinedunknown.append(listcorifdef)
                continue

            nodeifdef = listcorifdef[0]
            nodeifdefsibs = [sib for sib in nodeifdef.itersiblings()]

            error = 0
            for corifdef in listcorifdef[1:]:
                if not corifdef in nodeifdefsibs:
                    error = 1

            if error == 0:
                # check whether node is an argument or parameter
                parenttag = self.__getParentTag__(nodeifdef)
                if not parenttag in ['argument_list','parameter_list']:
                    error = 1

                firstsib = nodeifdefsibs[0]
                if firstsib.tag.split('}')[1] not in ['argument', 'param']:
                    error = 1
            if error == 1:
                listundisciplinedunknown.append(listcorifdef)
            else:
                if self.opts.verbose:
                    print('[INFO] param/argument pattern occured in line (%4s).' % nodeifdef.sourceline)
                listundisciplinedknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)

    PATEXP = 6 # 1 << 5 => 64
    def __checkExpression__(self, listifdefs):
        '''The method checks whether an #ifdef enframes an expression of a condition.'''
        listundisciplinedknown = list()
        listundisciplinedunknown = list()

        for listcorifdef in listifdefs:
            # pattern works only for #if-#endif combinations
            if len(listcorifdef) > 2:
                listundisciplinedunknown.append(listcorifdef)
                continue

            error = 0
            nodeifdef = listcorifdef[0]

            # get parent and check whether its tag is expr
            exppar = nodeifdef.getparent()
            exppartag = exppar.tag.split('}')[1]

            if not exppartag == 'expr':
                error = 1

            if error == 0:
                conpar = exppar.getparent()
                conpartag = conpar.tag.split('}')[1]

                if not conpartag == 'condition':
                    error = 1

            if error == 1:
                listundisciplinedunknown.append(listcorifdef)
            else:
                if self.opts.verbose:
                    print('[INFO] expression pattern occured in line (%4s).' % nodeifdef.sourceline)
                listundisciplinedknown.append(listcorifdef)

        assert len(listifdefs) == len(listundisciplinedknown)+len(listundisciplinedunknown)
        return (listundisciplinedknown, listundisciplinedunknown)


    def __iterateUnknownPatterns__(self, listifdefs, file):
        '''This method iterates of the unknown patterns and prints out information
        about the pattern: file and line.'''
        for ifdef in listifdefs:
            if self.opts.log:
                print('[INFO] Unknown pattern in file (%s) and line (%s)' % \
                        (file, ifdef[0].sourceline))

    def __checkDiscipline__(self, treeifdefs, file):
        '''This method checks a number of patterns in the given treeifdefs.
        The checks are in that order, that ifdef patterns not recognized
        are passed to the next pattern.'''
        listundisciplined = self.__createListFromTreeifdefs__(treeifdefs)
        listundisciplined = self.__filterConditionalPreprocessorDirectives(listundisciplined)
        if (listundisciplined == -1):
            print('[ERROR] Too many #endifs in file (%s)' % file)
            return
        if (listundisciplined == -2):
            print('[ERROR] Not enough #endifs in file (%s)' % file)
            return
        self.overallblocks += len(listundisciplined)

        # check TLS pattern, subset of sibling pattern
        if (self.opts.all or self.opts.check & (1 << DisciplinedAnnotations.PATTLS)):
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkStrictTLSCUPattern__(listifdefs)
            self.compilationunit += len(listdisciplined)
            self.disciplined += len(listdisciplined)

            # checking fd pattern (part of tls)
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkStrictTLSFDPattern__(listifdefs)
            self.functiontype += len(listdisciplined)
            self.disciplined += len(listdisciplined)

            # checking ill-formed compilation unit pattern
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkStrictPattern__(listifdefs)
            self.compilationunit += len(listdisciplined)
            self.disciplined += len(listdisciplined)

        # check if-then pattern
        if (self.opts.all or self.opts.check & (1 << DisciplinedAnnotations.PATIFTHEN)):
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkIfThenPattern__(listifdefs)
            self.wrapperif += len(listdisciplined)
            self.undisciplinedknown += len(listdisciplined)

        # check case pattern
        if (self.opts.all or self.opts.check & (1 << DisciplinedAnnotations.PATCASE)):
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkCasePattern__(listifdefs)
            self.conditionalcase += len(listdisciplined)
            self.undisciplinedknown += len(listdisciplined)

        # check else-if pattern
        if (self.opts.all or self.opts.check & (1 << DisciplinedAnnotations.PATELSEIF)):
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkElseIfPattern__(listifdefs)
            self.conditionalelif += len(listdisciplined)
            self.undisciplinedknown += len(listdisciplined)

        # check param pattern
        if (self.opts.all or self.opts.check & (1 << DisciplinedAnnotations.PATPARAM)):
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkParameter__(listifdefs)
            self.parameter += len(listdisciplined)
            self.undisciplinedknown += len(listdisciplined)

        # check expression pattern
        if (self.opts.all or self.opts.check & (1 << DisciplinedAnnotations.PATEXP)):
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkExpression__(listifdefs)
            self.expression += len(listdisciplined)
            self.undisciplinedknown += len(listdisciplined)

        # check sibling pattern; check this late because pattern might match for others as well
        if (self.opts.all or self.opts.check & (1 << DisciplinedAnnotations.PATSIB)):
            listifdefs = list(listundisciplined)
            (listdisciplined, listundisciplined) = \
                    self.__checkSiblingPattern__(listifdefs)
            self.siblings += len(listdisciplined)
            self.disciplined += len(listdisciplined)

        # wrap up listundisciplined
        self.__iterateUnknownPatterns__(listundisciplined, file)
        self.undisciplinedunknown += len(listundisciplined)


    def checkFile(self, file):
        try:
            tree = etree.parse(file)
            f = open(file, 'r')
        except etree.XMLSyntaxError:
            print('ERROR: file (%s) is not valid. Skipping it.' % file)
            return

        # get LOC
        self.loc += len(f.readlines())-2;

        # get root of the xml and iterate over it
        root = tree.getroot()
        treeifdefs = self.__getIfdefAnnotations__(root)
        
       
        try:
            self.__checkDiscipline__(treeifdefs, file)
        except:
            print('[ERROR]: file (%s) is not valid. Skipping it.' % file)
            return

    def checkFiles(self):
	if not ".xml" in self.opts.dir:
        	xmlfiles = returnFileNames(self.opts.dir, ['.xml'])
	else:
		xmlfiles = [self.opts.dir]
        for xmlfile in  xmlfiles:
            print('[INFO] checking file %s' % xmlfile)
            self.checkFile(xmlfile)
        #f = open("disciplined_stats.txt","a")
        #f.write(self.opts.dir
        #       +";LOC="+str(self.loc)
        #      +";CU="+str(self.compilationunit)
        #     +";FT="+str(self.functiontype)
        #    +";Siblings="+str(self.siblings)
        #   +";WIf="+str(self.wrapperif)
        #  +";Case="+str(self.conditionalcase)
        # +";Elif="+str(self.conditionalelif)
        # +";Param="+str(self.parameter)
        # +";Expr="+str(self.expression)
        # +";UndKnown="+str(self.undisciplinedknown)
        # +";UndUnknown="+str(self.undisciplinedunknown)
        # +";OB="+str(self.disciplined/(0.0+self.overallblocks))
        # +";"+str(self.overallblocks)+"\n")        
	self.results.append(str(self.undisciplinedknown + self.undisciplinedunknown))
	self.results.append(str(self.disciplined))
	print self.results
##################################################
if __name__ == '__main__':
    parser = OptionParser()
    (options, args) = parser.parse_args()
    DisciplinedAnnotations(args[0])
