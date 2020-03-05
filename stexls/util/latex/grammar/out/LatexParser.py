# Generated from LatexParser.g4 by ANTLR 4.8
# encoding: utf-8
from antlr4 import *
from io import StringIO
import sys
if sys.version_info[1] > 5:
	from typing import TextIO
else:
	from typing.io import TextIO


def serializedATN():
    with StringIO() as buf:
        buf.write("\3\u608b\ua72a\u8133\ub9ed\u417c\u3be7\u7786\u5964\3\r")
        buf.write("T\4\2\t\2\4\3\t\3\4\4\t\4\4\5\t\5\4\6\t\6\4\7\t\7\4\b")
        buf.write("\t\b\4\t\t\t\4\n\t\n\4\13\t\13\4\f\t\f\3\2\3\2\3\2\3\3")
        buf.write("\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\7\3(\n\3")
        buf.write("\f\3\16\3+\13\3\3\4\3\4\5\4/\n\4\3\5\3\5\5\5\63\n\5\3")
        buf.write("\5\3\5\3\5\3\6\3\6\3\6\3\6\3\6\3\7\3\7\3\7\3\7\3\7\3\b")
        buf.write("\3\b\3\t\3\t\3\n\3\n\3\n\3\n\3\13\3\13\3\13\3\13\3\f\3")
        buf.write("\f\6\fP\n\f\r\f\16\fQ\3\f\2\2\r\2\4\6\b\n\f\16\20\22\24")
        buf.write("\26\2\2\2R\2\30\3\2\2\2\4)\3\2\2\2\6,\3\2\2\2\b\60\3\2")
        buf.write("\2\2\n\67\3\2\2\2\f<\3\2\2\2\16A\3\2\2\2\20C\3\2\2\2\22")
        buf.write("E\3\2\2\2\24I\3\2\2\2\26O\3\2\2\2\30\31\5\4\3\2\31\32")
        buf.write("\7\2\2\3\32\3\3\2\2\2\33(\5\16\b\2\34(\5\b\5\2\35(\5\6")
        buf.write("\4\2\36(\5\20\t\2\37 \7\7\2\2 !\5\4\3\2!\"\7\b\2\2\"(")
        buf.write("\3\2\2\2#$\7\5\2\2$%\5\4\3\2%&\7\6\2\2&(\3\2\2\2\'\33")
        buf.write("\3\2\2\2\'\34\3\2\2\2\'\35\3\2\2\2\'\36\3\2\2\2\'\37\3")
        buf.write("\2\2\2\'#\3\2\2\2(+\3\2\2\2)\'\3\2\2\2)*\3\2\2\2*\5\3")
        buf.write("\2\2\2+)\3\2\2\2,.\7\f\2\2-/\5\26\f\2.-\3\2\2\2./\3\2")
        buf.write("\2\2/\7\3\2\2\2\60\62\5\n\6\2\61\63\5\26\f\2\62\61\3\2")
        buf.write("\2\2\62\63\3\2\2\2\63\64\3\2\2\2\64\65\5\4\3\2\65\66\5")
        buf.write("\f\7\2\66\t\3\2\2\2\678\7\n\2\289\7\7\2\29:\7\r\2\2:;")
        buf.write("\7\b\2\2;\13\3\2\2\2<=\7\13\2\2=>\7\7\2\2>?\7\r\2\2?@")
        buf.write("\7\b\2\2@\r\3\2\2\2AB\7\t\2\2B\17\3\2\2\2CD\7\r\2\2D\21")
        buf.write("\3\2\2\2EF\7\5\2\2FG\5\4\3\2GH\7\6\2\2H\23\3\2\2\2IJ\7")
        buf.write("\7\2\2JK\5\4\3\2KL\7\b\2\2L\25\3\2\2\2MP\5\24\13\2NP\5")
        buf.write("\22\n\2OM\3\2\2\2ON\3\2\2\2PQ\3\2\2\2QO\3\2\2\2QR\3\2")
        buf.write("\2\2R\27\3\2\2\2\b\').\62OQ")
        return buf.getvalue()


class LatexParser ( Parser ):

    grammarFileName = "LatexParser.g4"

    atn = ATNDeserializer().deserialize(serializedATN())

    decisionsToDFA = [ DFA(ds, i) for i, ds in enumerate(atn.decisionToState) ]

    sharedContextCache = PredictionContextCache()

    literalNames = [ "<INVALID>", "<INVALID>", "<INVALID>", "'['", "']'", 
                     "'{'", "'}'", "<INVALID>", "'\\begin'", "'\\end'" ]

    symbolicNames = [ "<INVALID>", "WS", "COMMENT", "OPEN_SQUARE", "CLOSED_SQUARE", 
                      "OPEN_BRACE", "CLOSED_BRACE", "MATH_ENV", "BEGIN", 
                      "END", "INLINE_ENV_NAME", "TOKEN" ]

    RULE_main = 0
    RULE_body = 1
    RULE_inlineEnv = 2
    RULE_env = 3
    RULE_envBegin = 4
    RULE_envEnd = 5
    RULE_math = 6
    RULE_token = 7
    RULE_oarg = 8
    RULE_rarg = 9
    RULE_args = 10

    ruleNames =  [ "main", "body", "inlineEnv", "env", "envBegin", "envEnd", 
                   "math", "token", "oarg", "rarg", "args" ]

    EOF = Token.EOF
    WS=1
    COMMENT=2
    OPEN_SQUARE=3
    CLOSED_SQUARE=4
    OPEN_BRACE=5
    CLOSED_BRACE=6
    MATH_ENV=7
    BEGIN=8
    END=9
    INLINE_ENV_NAME=10
    TOKEN=11

    def __init__(self, input:TokenStream, output:TextIO = sys.stdout):
        super().__init__(input, output)
        self.checkVersion("4.8")
        self._interp = ParserATNSimulator(self, self.atn, self.decisionsToDFA, self.sharedContextCache)
        self._predicates = None




    class MainContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def body(self):
            return self.getTypedRuleContext(LatexParser.BodyContext,0)


        def EOF(self):
            return self.getToken(LatexParser.EOF, 0)

        def getRuleIndex(self):
            return LatexParser.RULE_main

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterMain" ):
                listener.enterMain(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitMain" ):
                listener.exitMain(self)




    def main(self):

        localctx = LatexParser.MainContext(self, self._ctx, self.state)
        self.enterRule(localctx, 0, self.RULE_main)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 22
            self.body()
            self.state = 23
            self.match(LatexParser.EOF)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class BodyContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def math(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(LatexParser.MathContext)
            else:
                return self.getTypedRuleContext(LatexParser.MathContext,i)


        def env(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(LatexParser.EnvContext)
            else:
                return self.getTypedRuleContext(LatexParser.EnvContext,i)


        def inlineEnv(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(LatexParser.InlineEnvContext)
            else:
                return self.getTypedRuleContext(LatexParser.InlineEnvContext,i)


        def token(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(LatexParser.TokenContext)
            else:
                return self.getTypedRuleContext(LatexParser.TokenContext,i)


        def OPEN_BRACE(self, i:int=None):
            if i is None:
                return self.getTokens(LatexParser.OPEN_BRACE)
            else:
                return self.getToken(LatexParser.OPEN_BRACE, i)

        def body(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(LatexParser.BodyContext)
            else:
                return self.getTypedRuleContext(LatexParser.BodyContext,i)


        def CLOSED_BRACE(self, i:int=None):
            if i is None:
                return self.getTokens(LatexParser.CLOSED_BRACE)
            else:
                return self.getToken(LatexParser.CLOSED_BRACE, i)

        def OPEN_SQUARE(self, i:int=None):
            if i is None:
                return self.getTokens(LatexParser.OPEN_SQUARE)
            else:
                return self.getToken(LatexParser.OPEN_SQUARE, i)

        def CLOSED_SQUARE(self, i:int=None):
            if i is None:
                return self.getTokens(LatexParser.CLOSED_SQUARE)
            else:
                return self.getToken(LatexParser.CLOSED_SQUARE, i)

        def getRuleIndex(self):
            return LatexParser.RULE_body

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterBody" ):
                listener.enterBody(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitBody" ):
                listener.exitBody(self)




    def body(self):

        localctx = LatexParser.BodyContext(self, self._ctx, self.state)
        self.enterRule(localctx, 2, self.RULE_body)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 39
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while (((_la) & ~0x3f) == 0 and ((1 << _la) & ((1 << LatexParser.OPEN_SQUARE) | (1 << LatexParser.OPEN_BRACE) | (1 << LatexParser.MATH_ENV) | (1 << LatexParser.BEGIN) | (1 << LatexParser.INLINE_ENV_NAME) | (1 << LatexParser.TOKEN))) != 0):
                self.state = 37
                self._errHandler.sync(self)
                token = self._input.LA(1)
                if token in [LatexParser.MATH_ENV]:
                    self.state = 25
                    self.math()
                    pass
                elif token in [LatexParser.BEGIN]:
                    self.state = 26
                    self.env()
                    pass
                elif token in [LatexParser.INLINE_ENV_NAME]:
                    self.state = 27
                    self.inlineEnv()
                    pass
                elif token in [LatexParser.TOKEN]:
                    self.state = 28
                    self.token()
                    pass
                elif token in [LatexParser.OPEN_BRACE]:
                    self.state = 29
                    self.match(LatexParser.OPEN_BRACE)
                    self.state = 30
                    self.body()
                    self.state = 31
                    self.match(LatexParser.CLOSED_BRACE)
                    pass
                elif token in [LatexParser.OPEN_SQUARE]:
                    self.state = 33
                    self.match(LatexParser.OPEN_SQUARE)
                    self.state = 34
                    self.body()
                    self.state = 35
                    self.match(LatexParser.CLOSED_SQUARE)
                    pass
                else:
                    raise NoViableAltException(self)

                self.state = 41
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class InlineEnvContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def INLINE_ENV_NAME(self):
            return self.getToken(LatexParser.INLINE_ENV_NAME, 0)

        def args(self):
            return self.getTypedRuleContext(LatexParser.ArgsContext,0)


        def getRuleIndex(self):
            return LatexParser.RULE_inlineEnv

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterInlineEnv" ):
                listener.enterInlineEnv(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitInlineEnv" ):
                listener.exitInlineEnv(self)




    def inlineEnv(self):

        localctx = LatexParser.InlineEnvContext(self, self._ctx, self.state)
        self.enterRule(localctx, 4, self.RULE_inlineEnv)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 42
            self.match(LatexParser.INLINE_ENV_NAME)
            self.state = 44
            self._errHandler.sync(self)
            la_ = self._interp.adaptivePredict(self._input,2,self._ctx)
            if la_ == 1:
                self.state = 43
                self.args()


        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class EnvContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def envBegin(self):
            return self.getTypedRuleContext(LatexParser.EnvBeginContext,0)


        def body(self):
            return self.getTypedRuleContext(LatexParser.BodyContext,0)


        def envEnd(self):
            return self.getTypedRuleContext(LatexParser.EnvEndContext,0)


        def args(self):
            return self.getTypedRuleContext(LatexParser.ArgsContext,0)


        def getRuleIndex(self):
            return LatexParser.RULE_env

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterEnv" ):
                listener.enterEnv(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitEnv" ):
                listener.exitEnv(self)




    def env(self):

        localctx = LatexParser.EnvContext(self, self._ctx, self.state)
        self.enterRule(localctx, 6, self.RULE_env)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 46
            self.envBegin()
            self.state = 48
            self._errHandler.sync(self)
            la_ = self._interp.adaptivePredict(self._input,3,self._ctx)
            if la_ == 1:
                self.state = 47
                self.args()


            self.state = 50
            self.body()
            self.state = 51
            self.envEnd()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class EnvBeginContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def BEGIN(self):
            return self.getToken(LatexParser.BEGIN, 0)

        def OPEN_BRACE(self):
            return self.getToken(LatexParser.OPEN_BRACE, 0)

        def TOKEN(self):
            return self.getToken(LatexParser.TOKEN, 0)

        def CLOSED_BRACE(self):
            return self.getToken(LatexParser.CLOSED_BRACE, 0)

        def getRuleIndex(self):
            return LatexParser.RULE_envBegin

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterEnvBegin" ):
                listener.enterEnvBegin(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitEnvBegin" ):
                listener.exitEnvBegin(self)




    def envBegin(self):

        localctx = LatexParser.EnvBeginContext(self, self._ctx, self.state)
        self.enterRule(localctx, 8, self.RULE_envBegin)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 53
            self.match(LatexParser.BEGIN)
            self.state = 54
            self.match(LatexParser.OPEN_BRACE)
            self.state = 55
            self.match(LatexParser.TOKEN)
            self.state = 56
            self.match(LatexParser.CLOSED_BRACE)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class EnvEndContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def END(self):
            return self.getToken(LatexParser.END, 0)

        def OPEN_BRACE(self):
            return self.getToken(LatexParser.OPEN_BRACE, 0)

        def TOKEN(self):
            return self.getToken(LatexParser.TOKEN, 0)

        def CLOSED_BRACE(self):
            return self.getToken(LatexParser.CLOSED_BRACE, 0)

        def getRuleIndex(self):
            return LatexParser.RULE_envEnd

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterEnvEnd" ):
                listener.enterEnvEnd(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitEnvEnd" ):
                listener.exitEnvEnd(self)




    def envEnd(self):

        localctx = LatexParser.EnvEndContext(self, self._ctx, self.state)
        self.enterRule(localctx, 10, self.RULE_envEnd)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 58
            self.match(LatexParser.END)
            self.state = 59
            self.match(LatexParser.OPEN_BRACE)
            self.state = 60
            self.match(LatexParser.TOKEN)
            self.state = 61
            self.match(LatexParser.CLOSED_BRACE)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class MathContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def MATH_ENV(self):
            return self.getToken(LatexParser.MATH_ENV, 0)

        def getRuleIndex(self):
            return LatexParser.RULE_math

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterMath" ):
                listener.enterMath(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitMath" ):
                listener.exitMath(self)




    def math(self):

        localctx = LatexParser.MathContext(self, self._ctx, self.state)
        self.enterRule(localctx, 12, self.RULE_math)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 63
            self.match(LatexParser.MATH_ENV)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class TokenContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def TOKEN(self):
            return self.getToken(LatexParser.TOKEN, 0)

        def getRuleIndex(self):
            return LatexParser.RULE_token

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterToken" ):
                listener.enterToken(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitToken" ):
                listener.exitToken(self)




    def token(self):

        localctx = LatexParser.TokenContext(self, self._ctx, self.state)
        self.enterRule(localctx, 14, self.RULE_token)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 65
            self.match(LatexParser.TOKEN)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class OargContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def OPEN_SQUARE(self):
            return self.getToken(LatexParser.OPEN_SQUARE, 0)

        def body(self):
            return self.getTypedRuleContext(LatexParser.BodyContext,0)


        def CLOSED_SQUARE(self):
            return self.getToken(LatexParser.CLOSED_SQUARE, 0)

        def getRuleIndex(self):
            return LatexParser.RULE_oarg

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterOarg" ):
                listener.enterOarg(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitOarg" ):
                listener.exitOarg(self)




    def oarg(self):

        localctx = LatexParser.OargContext(self, self._ctx, self.state)
        self.enterRule(localctx, 16, self.RULE_oarg)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 67
            self.match(LatexParser.OPEN_SQUARE)
            self.state = 68
            self.body()
            self.state = 69
            self.match(LatexParser.CLOSED_SQUARE)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class RargContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def OPEN_BRACE(self):
            return self.getToken(LatexParser.OPEN_BRACE, 0)

        def body(self):
            return self.getTypedRuleContext(LatexParser.BodyContext,0)


        def CLOSED_BRACE(self):
            return self.getToken(LatexParser.CLOSED_BRACE, 0)

        def getRuleIndex(self):
            return LatexParser.RULE_rarg

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterRarg" ):
                listener.enterRarg(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitRarg" ):
                listener.exitRarg(self)




    def rarg(self):

        localctx = LatexParser.RargContext(self, self._ctx, self.state)
        self.enterRule(localctx, 18, self.RULE_rarg)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 71
            self.match(LatexParser.OPEN_BRACE)
            self.state = 72
            self.body()
            self.state = 73
            self.match(LatexParser.CLOSED_BRACE)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ArgsContext(ParserRuleContext):

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def rarg(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(LatexParser.RargContext)
            else:
                return self.getTypedRuleContext(LatexParser.RargContext,i)


        def oarg(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(LatexParser.OargContext)
            else:
                return self.getTypedRuleContext(LatexParser.OargContext,i)


        def getRuleIndex(self):
            return LatexParser.RULE_args

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterArgs" ):
                listener.enterArgs(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitArgs" ):
                listener.exitArgs(self)




    def args(self):

        localctx = LatexParser.ArgsContext(self, self._ctx, self.state)
        self.enterRule(localctx, 20, self.RULE_args)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 77 
            self._errHandler.sync(self)
            _alt = 1
            while _alt!=2 and _alt!=ATN.INVALID_ALT_NUMBER:
                if _alt == 1:
                    self.state = 77
                    self._errHandler.sync(self)
                    token = self._input.LA(1)
                    if token in [LatexParser.OPEN_BRACE]:
                        self.state = 75
                        self.rarg()
                        pass
                    elif token in [LatexParser.OPEN_SQUARE]:
                        self.state = 76
                        self.oarg()
                        pass
                    else:
                        raise NoViableAltException(self)


                else:
                    raise NoViableAltException(self)
                self.state = 79 
                self._errHandler.sync(self)
                _alt = self._interp.adaptivePredict(self._input,5,self._ctx)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx





