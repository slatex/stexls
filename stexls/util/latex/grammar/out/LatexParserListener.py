# Generated from LatexParser.g4 by ANTLR 4.8
from antlr4 import *
if __name__ is not None and "." in __name__:
    from .LatexParser import LatexParser
else:
    from LatexParser import LatexParser

# This class defines a complete listener for a parse tree produced by LatexParser.
class LatexParserListener(ParseTreeListener):

    # Enter a parse tree produced by LatexParser#main.
    def enterMain(self, ctx:LatexParser.MainContext):
        pass

    # Exit a parse tree produced by LatexParser#main.
    def exitMain(self, ctx:LatexParser.MainContext):
        pass


    # Enter a parse tree produced by LatexParser#body.
    def enterBody(self, ctx:LatexParser.BodyContext):
        pass

    # Exit a parse tree produced by LatexParser#body.
    def exitBody(self, ctx:LatexParser.BodyContext):
        pass


    # Enter a parse tree produced by LatexParser#inlineEnv.
    def enterInlineEnv(self, ctx:LatexParser.InlineEnvContext):
        pass

    # Exit a parse tree produced by LatexParser#inlineEnv.
    def exitInlineEnv(self, ctx:LatexParser.InlineEnvContext):
        pass


    # Enter a parse tree produced by LatexParser#env.
    def enterEnv(self, ctx:LatexParser.EnvContext):
        pass

    # Exit a parse tree produced by LatexParser#env.
    def exitEnv(self, ctx:LatexParser.EnvContext):
        pass


    # Enter a parse tree produced by LatexParser#envBegin.
    def enterEnvBegin(self, ctx:LatexParser.EnvBeginContext):
        pass

    # Exit a parse tree produced by LatexParser#envBegin.
    def exitEnvBegin(self, ctx:LatexParser.EnvBeginContext):
        pass


    # Enter a parse tree produced by LatexParser#envEnd.
    def enterEnvEnd(self, ctx:LatexParser.EnvEndContext):
        pass

    # Exit a parse tree produced by LatexParser#envEnd.
    def exitEnvEnd(self, ctx:LatexParser.EnvEndContext):
        pass


    # Enter a parse tree produced by LatexParser#math.
    def enterMath(self, ctx:LatexParser.MathContext):
        pass

    # Exit a parse tree produced by LatexParser#math.
    def exitMath(self, ctx:LatexParser.MathContext):
        pass


    # Enter a parse tree produced by LatexParser#token.
    def enterToken(self, ctx:LatexParser.TokenContext):
        pass

    # Exit a parse tree produced by LatexParser#token.
    def exitToken(self, ctx:LatexParser.TokenContext):
        pass


    # Enter a parse tree produced by LatexParser#oarg.
    def enterOarg(self, ctx:LatexParser.OargContext):
        pass

    # Exit a parse tree produced by LatexParser#oarg.
    def exitOarg(self, ctx:LatexParser.OargContext):
        pass


    # Enter a parse tree produced by LatexParser#rarg.
    def enterRarg(self, ctx:LatexParser.RargContext):
        pass

    # Exit a parse tree produced by LatexParser#rarg.
    def exitRarg(self, ctx:LatexParser.RargContext):
        pass


    # Enter a parse tree produced by LatexParser#args.
    def enterArgs(self, ctx:LatexParser.ArgsContext):
        pass

    # Exit a parse tree produced by LatexParser#args.
    def exitArgs(self, ctx:LatexParser.ArgsContext):
        pass



del LatexParser