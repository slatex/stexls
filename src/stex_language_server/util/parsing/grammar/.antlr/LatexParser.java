// Generated from /home/marian/projects/trefier/trefier-backend/src/stex_language_server/util/parsing/grammar/LatexParser.g4 by ANTLR 4.7.1
import org.antlr.v4.runtime.atn.*;
import org.antlr.v4.runtime.dfa.DFA;
import org.antlr.v4.runtime.*;
import org.antlr.v4.runtime.misc.*;
import org.antlr.v4.runtime.tree.*;
import java.util.List;
import java.util.Iterator;
import java.util.ArrayList;

@SuppressWarnings({"all", "warnings", "unchecked", "unused", "cast"})
public class LatexParser extends Parser {
	static { RuntimeMetaData.checkVersion("4.7.1", RuntimeMetaData.VERSION); }

	protected static final DFA[] _decisionToDFA;
	protected static final PredictionContextCache _sharedContextCache =
		new PredictionContextCache();
	public static final int
		WS=1, COMMENT=2, OPEN_SQUARE=3, CLOSED_SQUARE=4, OPEN_BRACE=5, CLOSED_BRACE=6, 
		MATH_ENV=7, BEGIN=8, END=9, INLINE_ENV_NAME=10, TOKEN=11;
	public static final int
		RULE_main = 0, RULE_body = 1, RULE_inlineEnv = 2, RULE_env = 3, RULE_envBegin = 4, 
		RULE_envEnd = 5, RULE_math = 6, RULE_token = 7, RULE_oarg = 8, RULE_rarg = 9, 
		RULE_args = 10;
	public static final String[] ruleNames = {
		"main", "body", "inlineEnv", "env", "envBegin", "envEnd", "math", "token", 
		"oarg", "rarg", "args"
	};

	private static final String[] _LITERAL_NAMES = {
		null, null, null, "'['", "']'", "'{'", "'}'", null, "'\\begin'", "'\\end'"
	};
	private static final String[] _SYMBOLIC_NAMES = {
		null, "WS", "COMMENT", "OPEN_SQUARE", "CLOSED_SQUARE", "OPEN_BRACE", "CLOSED_BRACE", 
		"MATH_ENV", "BEGIN", "END", "INLINE_ENV_NAME", "TOKEN"
	};
	public static final Vocabulary VOCABULARY = new VocabularyImpl(_LITERAL_NAMES, _SYMBOLIC_NAMES);

	/**
	 * @deprecated Use {@link #VOCABULARY} instead.
	 */
	@Deprecated
	public static final String[] tokenNames;
	static {
		tokenNames = new String[_SYMBOLIC_NAMES.length];
		for (int i = 0; i < tokenNames.length; i++) {
			tokenNames[i] = VOCABULARY.getLiteralName(i);
			if (tokenNames[i] == null) {
				tokenNames[i] = VOCABULARY.getSymbolicName(i);
			}

			if (tokenNames[i] == null) {
				tokenNames[i] = "<INVALID>";
			}
		}
	}

	@Override
	@Deprecated
	public String[] getTokenNames() {
		return tokenNames;
	}

	@Override

	public Vocabulary getVocabulary() {
		return VOCABULARY;
	}

	@Override
	public String getGrammarFileName() { return "LatexParser.g4"; }

	@Override
	public String[] getRuleNames() { return ruleNames; }

	@Override
	public String getSerializedATN() { return _serializedATN; }

	@Override
	public ATN getATN() { return _ATN; }

	public LatexParser(TokenStream input) {
		super(input);
		_interp = new ParserATNSimulator(this,_ATN,_decisionToDFA,_sharedContextCache);
	}
	public static class MainContext extends ParserRuleContext {
		public BodyContext body() {
			return getRuleContext(BodyContext.class,0);
		}
		public TerminalNode EOF() { return getToken(LatexParser.EOF, 0); }
		public MainContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_main; }
	}

	public final MainContext main() throws RecognitionException {
		MainContext _localctx = new MainContext(_ctx, getState());
		enterRule(_localctx, 0, RULE_main);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(22);
			body();
			setState(23);
			match(EOF);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class BodyContext extends ParserRuleContext {
		public List<MathContext> math() {
			return getRuleContexts(MathContext.class);
		}
		public MathContext math(int i) {
			return getRuleContext(MathContext.class,i);
		}
		public List<EnvContext> env() {
			return getRuleContexts(EnvContext.class);
		}
		public EnvContext env(int i) {
			return getRuleContext(EnvContext.class,i);
		}
		public List<InlineEnvContext> inlineEnv() {
			return getRuleContexts(InlineEnvContext.class);
		}
		public InlineEnvContext inlineEnv(int i) {
			return getRuleContext(InlineEnvContext.class,i);
		}
		public List<TokenContext> token() {
			return getRuleContexts(TokenContext.class);
		}
		public TokenContext token(int i) {
			return getRuleContext(TokenContext.class,i);
		}
		public List<BodyContext> body() {
			return getRuleContexts(BodyContext.class);
		}
		public BodyContext body(int i) {
			return getRuleContext(BodyContext.class,i);
		}
		public BodyContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_body; }
	}

	public final BodyContext body() throws RecognitionException {
		BodyContext _localctx = new BodyContext(_ctx, getState());
		enterRule(_localctx, 2, RULE_body);
		int _la;
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(39);
			_errHandler.sync(this);
			_la = _input.LA(1);
			while ((((_la) & ~0x3f) == 0 && ((1L << _la) & ((1L << OPEN_SQUARE) | (1L << OPEN_BRACE) | (1L << MATH_ENV) | (1L << BEGIN) | (1L << INLINE_ENV_NAME) | (1L << TOKEN))) != 0)) {
				{
				setState(37);
				_errHandler.sync(this);
				switch (_input.LA(1)) {
				case MATH_ENV:
					{
					setState(25);
					math();
					}
					break;
				case BEGIN:
					{
					setState(26);
					env();
					}
					break;
				case INLINE_ENV_NAME:
					{
					setState(27);
					inlineEnv();
					}
					break;
				case TOKEN:
					{
					setState(28);
					token();
					}
					break;
				case OPEN_BRACE:
					{
					setState(29);
					match(OPEN_BRACE);
					setState(30);
					body();
					setState(31);
					match(CLOSED_BRACE);
					}
					break;
				case OPEN_SQUARE:
					{
					setState(33);
					match(OPEN_SQUARE);
					setState(34);
					body();
					setState(35);
					match(CLOSED_SQUARE);
					}
					break;
				default:
					throw new NoViableAltException(this);
				}
				}
				setState(41);
				_errHandler.sync(this);
				_la = _input.LA(1);
			}
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class InlineEnvContext extends ParserRuleContext {
		public TerminalNode INLINE_ENV_NAME() { return getToken(LatexParser.INLINE_ENV_NAME, 0); }
		public ArgsContext args() {
			return getRuleContext(ArgsContext.class,0);
		}
		public InlineEnvContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_inlineEnv; }
	}

	public final InlineEnvContext inlineEnv() throws RecognitionException {
		InlineEnvContext _localctx = new InlineEnvContext(_ctx, getState());
		enterRule(_localctx, 4, RULE_inlineEnv);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(42);
			match(INLINE_ENV_NAME);
			setState(44);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,2,_ctx) ) {
			case 1:
				{
				setState(43);
				args();
				}
				break;
			}
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class EnvContext extends ParserRuleContext {
		public EnvBeginContext envBegin() {
			return getRuleContext(EnvBeginContext.class,0);
		}
		public BodyContext body() {
			return getRuleContext(BodyContext.class,0);
		}
		public EnvEndContext envEnd() {
			return getRuleContext(EnvEndContext.class,0);
		}
		public ArgsContext args() {
			return getRuleContext(ArgsContext.class,0);
		}
		public EnvContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_env; }
	}

	public final EnvContext env() throws RecognitionException {
		EnvContext _localctx = new EnvContext(_ctx, getState());
		enterRule(_localctx, 6, RULE_env);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(46);
			envBegin();
			setState(48);
			_errHandler.sync(this);
			switch ( getInterpreter().adaptivePredict(_input,3,_ctx) ) {
			case 1:
				{
				setState(47);
				args();
				}
				break;
			}
			setState(50);
			body();
			setState(51);
			envEnd();
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class EnvBeginContext extends ParserRuleContext {
		public TerminalNode BEGIN() { return getToken(LatexParser.BEGIN, 0); }
		public TerminalNode TOKEN() { return getToken(LatexParser.TOKEN, 0); }
		public EnvBeginContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_envBegin; }
	}

	public final EnvBeginContext envBegin() throws RecognitionException {
		EnvBeginContext _localctx = new EnvBeginContext(_ctx, getState());
		enterRule(_localctx, 8, RULE_envBegin);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(53);
			match(BEGIN);
			setState(54);
			match(OPEN_BRACE);
			setState(55);
			match(TOKEN);
			setState(56);
			match(CLOSED_BRACE);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class EnvEndContext extends ParserRuleContext {
		public TerminalNode END() { return getToken(LatexParser.END, 0); }
		public TerminalNode TOKEN() { return getToken(LatexParser.TOKEN, 0); }
		public EnvEndContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_envEnd; }
	}

	public final EnvEndContext envEnd() throws RecognitionException {
		EnvEndContext _localctx = new EnvEndContext(_ctx, getState());
		enterRule(_localctx, 10, RULE_envEnd);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(58);
			match(END);
			setState(59);
			match(OPEN_BRACE);
			setState(60);
			match(TOKEN);
			setState(61);
			match(CLOSED_BRACE);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class MathContext extends ParserRuleContext {
		public TerminalNode MATH_ENV() { return getToken(LatexParser.MATH_ENV, 0); }
		public MathContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_math; }
	}

	public final MathContext math() throws RecognitionException {
		MathContext _localctx = new MathContext(_ctx, getState());
		enterRule(_localctx, 12, RULE_math);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(63);
			match(MATH_ENV);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class TokenContext extends ParserRuleContext {
		public TerminalNode TOKEN() { return getToken(LatexParser.TOKEN, 0); }
		public TokenContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_token; }
	}

	public final TokenContext token() throws RecognitionException {
		TokenContext _localctx = new TokenContext(_ctx, getState());
		enterRule(_localctx, 14, RULE_token);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(65);
			match(TOKEN);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class OargContext extends ParserRuleContext {
		public BodyContext body() {
			return getRuleContext(BodyContext.class,0);
		}
		public OargContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_oarg; }
	}

	public final OargContext oarg() throws RecognitionException {
		OargContext _localctx = new OargContext(_ctx, getState());
		enterRule(_localctx, 16, RULE_oarg);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(67);
			match(OPEN_SQUARE);
			setState(68);
			body();
			setState(69);
			match(CLOSED_SQUARE);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class RargContext extends ParserRuleContext {
		public BodyContext body() {
			return getRuleContext(BodyContext.class,0);
		}
		public RargContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_rarg; }
	}

	public final RargContext rarg() throws RecognitionException {
		RargContext _localctx = new RargContext(_ctx, getState());
		enterRule(_localctx, 18, RULE_rarg);
		try {
			enterOuterAlt(_localctx, 1);
			{
			setState(71);
			match(OPEN_BRACE);
			setState(72);
			body();
			setState(73);
			match(CLOSED_BRACE);
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static class ArgsContext extends ParserRuleContext {
		public List<RargContext> rarg() {
			return getRuleContexts(RargContext.class);
		}
		public RargContext rarg(int i) {
			return getRuleContext(RargContext.class,i);
		}
		public List<OargContext> oarg() {
			return getRuleContexts(OargContext.class);
		}
		public OargContext oarg(int i) {
			return getRuleContext(OargContext.class,i);
		}
		public ArgsContext(ParserRuleContext parent, int invokingState) {
			super(parent, invokingState);
		}
		@Override public int getRuleIndex() { return RULE_args; }
	}

	public final ArgsContext args() throws RecognitionException {
		ArgsContext _localctx = new ArgsContext(_ctx, getState());
		enterRule(_localctx, 20, RULE_args);
		try {
			int _alt;
			enterOuterAlt(_localctx, 1);
			{
			setState(77); 
			_errHandler.sync(this);
			_alt = 1;
			do {
				switch (_alt) {
				case 1:
					{
					setState(77);
					_errHandler.sync(this);
					switch (_input.LA(1)) {
					case OPEN_BRACE:
						{
						setState(75);
						rarg();
						}
						break;
					case OPEN_SQUARE:
						{
						setState(76);
						oarg();
						}
						break;
					default:
						throw new NoViableAltException(this);
					}
					}
					break;
				default:
					throw new NoViableAltException(this);
				}
				setState(79); 
				_errHandler.sync(this);
				_alt = getInterpreter().adaptivePredict(_input,5,_ctx);
			} while ( _alt!=2 && _alt!=org.antlr.v4.runtime.atn.ATN.INVALID_ALT_NUMBER );
			}
		}
		catch (RecognitionException re) {
			_localctx.exception = re;
			_errHandler.reportError(this, re);
			_errHandler.recover(this, re);
		}
		finally {
			exitRule();
		}
		return _localctx;
	}

	public static final String _serializedATN =
		"\3\u608b\ua72a\u8133\ub9ed\u417c\u3be7\u7786\u5964\3\rT\4\2\t\2\4\3\t"+
		"\3\4\4\t\4\4\5\t\5\4\6\t\6\4\7\t\7\4\b\t\b\4\t\t\t\4\n\t\n\4\13\t\13\4"+
		"\f\t\f\3\2\3\2\3\2\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\3\7\3"+
		"(\n\3\f\3\16\3+\13\3\3\4\3\4\5\4/\n\4\3\5\3\5\5\5\63\n\5\3\5\3\5\3\5\3"+
		"\6\3\6\3\6\3\6\3\6\3\7\3\7\3\7\3\7\3\7\3\b\3\b\3\t\3\t\3\n\3\n\3\n\3\n"+
		"\3\13\3\13\3\13\3\13\3\f\3\f\6\fP\n\f\r\f\16\fQ\3\f\2\2\r\2\4\6\b\n\f"+
		"\16\20\22\24\26\2\2\2R\2\30\3\2\2\2\4)\3\2\2\2\6,\3\2\2\2\b\60\3\2\2\2"+
		"\n\67\3\2\2\2\f<\3\2\2\2\16A\3\2\2\2\20C\3\2\2\2\22E\3\2\2\2\24I\3\2\2"+
		"\2\26O\3\2\2\2\30\31\5\4\3\2\31\32\7\2\2\3\32\3\3\2\2\2\33(\5\16\b\2\34"+
		"(\5\b\5\2\35(\5\6\4\2\36(\5\20\t\2\37 \7\7\2\2 !\5\4\3\2!\"\7\b\2\2\""+
		"(\3\2\2\2#$\7\5\2\2$%\5\4\3\2%&\7\6\2\2&(\3\2\2\2\'\33\3\2\2\2\'\34\3"+
		"\2\2\2\'\35\3\2\2\2\'\36\3\2\2\2\'\37\3\2\2\2\'#\3\2\2\2(+\3\2\2\2)\'"+
		"\3\2\2\2)*\3\2\2\2*\5\3\2\2\2+)\3\2\2\2,.\7\f\2\2-/\5\26\f\2.-\3\2\2\2"+
		"./\3\2\2\2/\7\3\2\2\2\60\62\5\n\6\2\61\63\5\26\f\2\62\61\3\2\2\2\62\63"+
		"\3\2\2\2\63\64\3\2\2\2\64\65\5\4\3\2\65\66\5\f\7\2\66\t\3\2\2\2\678\7"+
		"\n\2\289\7\7\2\29:\7\r\2\2:;\7\b\2\2;\13\3\2\2\2<=\7\13\2\2=>\7\7\2\2"+
		">?\7\r\2\2?@\7\b\2\2@\r\3\2\2\2AB\7\t\2\2B\17\3\2\2\2CD\7\r\2\2D\21\3"+
		"\2\2\2EF\7\5\2\2FG\5\4\3\2GH\7\6\2\2H\23\3\2\2\2IJ\7\7\2\2JK\5\4\3\2K"+
		"L\7\b\2\2L\25\3\2\2\2MP\5\24\13\2NP\5\22\n\2OM\3\2\2\2ON\3\2\2\2PQ\3\2"+
		"\2\2QO\3\2\2\2QR\3\2\2\2R\27\3\2\2\2\b\').\62OQ";
	public static final ATN _ATN =
		new ATNDeserializer().deserialize(_serializedATN.toCharArray());
	static {
		_decisionToDFA = new DFA[_ATN.getNumberOfDecisions()];
		for (int i = 0; i < _ATN.getNumberOfDecisions(); i++) {
			_decisionToDFA[i] = new DFA(_ATN.getDecisionState(i), i);
		}
	}
}