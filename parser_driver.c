#define _POSIX_C_SOURCE 200809L
#include <limits.h>
#include <locale.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <lalr_parser.tab.h>

typedef struct yy_buffer_state *YY_BUFFER_STATE;
extern YY_BUFFER_STATE yy_scan_bytes(const char *bytes, int length);
extern void yy_delete_buffer(YY_BUFFER_STATE buffer);
extern int yylex(void);
extern char *yytext;
extern int yydebug;
int yyparse(void);

static int json_mode;
static char parse_error[512];

typedef struct {
    char *type;
    char *lexeme;
} Token;

typedef struct {
    Token *items;
    size_t count;
    size_t capacity;
} TokenList;

typedef struct {
    const char *lhs;
    const char *rhs[7];
    size_t rhs_count;
    const char *text;
} Production;

static const Production productions[] = {
    {"", {NULL}, 0, ""},
    {"program", {"statements", NULL}, 1, "program -> statements"},
    {"statements", {"statements", "statement", NULL}, 2, "statements -> statements statement"},
    {"statements", {"statement", NULL}, 1, "statements -> statement"},
    {"statement", {"assignment", NULL}, 1, "statement -> assignment"},
    {"statement", {"conditional", NULL}, 1, "statement -> conditional"},
    {"assignment", {"ID", "ASSIGN", "expression", "SEMICOLON", NULL}, 4, "assignment -> ID ASSIGN expression SEMICOLON"},
    {"expression", {"expression", "PLUS", "term", NULL}, 3, "expression -> expression PLUS term"},
    {"expression", {"expression", "MINUS", "term", NULL}, 3, "expression -> expression MINUS term"},
    {"expression", {"term", NULL}, 1, "expression -> term"},
    {"term", {"term", "MULT", "factor", NULL}, 3, "term -> term MULT factor"},
    {"term", {"term", "DIV", "factor", NULL}, 3, "term -> term DIV factor"},
    {"term", {"factor", NULL}, 1, "term -> factor"},
    {"factor", {"ID", NULL}, 1, "factor -> ID"},
    {"factor", {"NUM", NULL}, 1, "factor -> NUM"},
    {"factor", {"LPAREN", "expression", "RPAREN", NULL}, 3, "factor -> LPAREN expression RPAREN"},
    {"conditional", {"IF", "LPAREN", "condition", "RPAREN", "statement", NULL}, 5, "conditional -> IF LPAREN condition RPAREN statement"},
    {"conditional", {"IF", "LPAREN", "condition", "RPAREN", "statement", "ELSE", "statement"}, 7, "conditional -> IF LPAREN condition RPAREN statement ELSE statement"},
    {"condition", {"expression", "relational_operator", "expression", NULL}, 3, "condition -> expression relational_operator expression"},
    {"relational_operator", {"LT", NULL}, 1, "relational_operator -> LT"},
    {"relational_operator", {"GT", NULL}, 1, "relational_operator -> GT"},
    {"relational_operator", {"LE", NULL}, 1, "relational_operator -> LE"},
    {"relational_operator", {"GE", NULL}, 1, "relational_operator -> GE"},
    {"relational_operator", {"EQ", NULL}, 1, "relational_operator -> EQ"},
    {"relational_operator", {"NE", NULL}, 1, "relational_operator -> NE"},
};

typedef enum { INIT, SHIFT, REDUCE, ACCEPT, ERROR } Action;

typedef struct {
    Action action;
    int state;
    int token_index;
    int production;
    int goto_state;
    char **stack;
    size_t stack_count;
    size_t input_index;
} TraceStep;

typedef struct {
    TraceStep *items;
    size_t count;
    size_t capacity;
} Trace;

typedef struct {
    char **symbols;
    int *states;
    size_t count;
    size_t capacity;
} ParserStack;

static char *copy_string(const char *s) {
    size_t n = strlen(s) + 1;
    char *copy = malloc(n);
    if (copy) memcpy(copy, s, n);
    return copy;
}

static const char *token_name(int token) {
    switch (token) {
        case IF: return "IF";
        case ELSE: return "ELSE";
        case ID: return "ID";
        case NUM: return "NUM";
        case ASSIGN: return "ASSIGN";
        case PLUS: return "PLUS";
        case MINUS: return "MINUS";
        case MULT: return "MULT";
        case DIV: return "DIV";
        case LT: return "LT";
        case GT: return "GT";
        case LE: return "LE";
        case GE: return "GE";
        case EQ: return "EQ";
        case NE: return "NE";
        case LPAREN: return "LPAREN";
        case RPAREN: return "RPAREN";
        case SEMICOLON: return "SEMICOLON";
        case INVALID: return "INVALID";
        default: return "UNKNOWN";
    }
}

static int append_token(TokenList *list, int type, const char *lexeme) {
    if (list->count == list->capacity) {
        size_t capacity = list->capacity ? list->capacity * 2 : 32;
        Token *items = realloc(list->items, capacity * sizeof(*items));
        if (!items) return 0;
        list->items = items;
        list->capacity = capacity;
    }
    Token *item = &list->items[list->count];
    item->type = copy_string(token_name(type));
    item->lexeme = copy_string(lexeme ? lexeme : "");
    if (!item->type || !item->lexeme) return 0;
    list->count++;
    return 1;
}

static void free_tokens(TokenList *list) {
    for (size_t i = 0; i < list->count; i++) {
        free(list->items[i].type);
        free(list->items[i].lexeme);
    }
    free(list->items);
}

static int tokenize(const char *source, size_t length, TokenList *tokens) {
    if (length > INT_MAX) return 0;
    YY_BUFFER_STATE buffer = yy_scan_bytes(source, (int)length);
    if (!buffer) return 0;
    int type;
    int ok = 1;
    while ((type = yylex()) != 0) {
        if (!append_token(tokens, type, yytext)) {
            ok = 0;
            break;
        }
    }
    yy_delete_buffer(buffer);
    return ok;
}

static int stack_push(ParserStack *stack, const char *symbol, int state) {
    if (stack->count == stack->capacity) {
        size_t capacity = stack->capacity ? stack->capacity * 2 : 32;
        char **symbols = realloc(stack->symbols, capacity * sizeof(*symbols));
        if (!symbols) return 0;
        stack->symbols = symbols;
        int *states = realloc(stack->states, (capacity + 1) * sizeof(*states));
        if (!states) return 0;
        stack->states = states;
        stack->capacity = capacity;
    }
    stack->symbols[stack->count] = copy_string(symbol);
    if (!stack->symbols[stack->count]) return 0;
    stack->count++;
    stack->states[stack->count] = state;
    return 1;
}

static void stack_pop(ParserStack *stack, size_t count) {
    while (count-- && stack->count) free(stack->symbols[--stack->count]);
}

static int add_step(Trace *trace, Action action, int state, int token_index,
                    int production, int goto_state, const ParserStack *stack,
                    size_t input_index) {
    if (trace->count == trace->capacity) {
        size_t capacity = trace->capacity ? trace->capacity * 2 : 32;
        TraceStep *items = realloc(trace->items, capacity * sizeof(*items));
        if (!items) return 0;
        trace->items = items;
        trace->capacity = capacity;
    }
    TraceStep *step = &trace->items[trace->count];
    memset(step, 0, sizeof(*step));
    step->action = action;
    step->state = state;
    step->token_index = token_index;
    step->production = production;
    step->goto_state = goto_state;
    step->input_index = input_index;
    step->stack_count = stack->count * 2 + 1;
    step->stack = calloc(step->stack_count, sizeof(*step->stack));
    if (!step->stack) return 0;
    char state_text[32];
    snprintf(state_text, sizeof(state_text), "%d", stack->states[0]);
    step->stack[0] = copy_string(state_text);
    if (!step->stack[0]) return 0;
    for (size_t i = 0; i < stack->count; i++) {
        step->stack[i * 2 + 1] = copy_string(stack->symbols[i]);
        snprintf(state_text, sizeof(state_text), "%d", stack->states[i + 1]);
        step->stack[i * 2 + 2] = copy_string(state_text);
        if (!step->stack[i * 2 + 1] || !step->stack[i * 2 + 2]) return 0;
    }
    trace->count++;
    return 1;
}

static const char *action_name(Action action) {
    static const char *names[] = {"INIT", "SHIFT", "REDUCE", "ACCEPT", "ERROR"};
    return names[action];
}

static size_t utf8_length(const unsigned char *p) {
    if (p[0] >= 0xc2 && p[0] <= 0xdf && (p[1] & 0xc0) == 0x80) return 2;
    if (p[0] == 0xe0 && p[1] >= 0xa0 && p[1] <= 0xbf && (p[2] & 0xc0) == 0x80) return 3;
    if (((p[0] >= 0xe1 && p[0] <= 0xec) || (p[0] >= 0xee && p[0] <= 0xef)) &&
        (p[1] & 0xc0) == 0x80 && (p[2] & 0xc0) == 0x80) return 3;
    if (p[0] == 0xed && p[1] >= 0x80 && p[1] <= 0x9f && (p[2] & 0xc0) == 0x80) return 3;
    if (p[0] == 0xf0 && p[1] >= 0x90 && p[1] <= 0xbf &&
        (p[2] & 0xc0) == 0x80 && (p[3] & 0xc0) == 0x80) return 4;
    if (p[0] >= 0xf1 && p[0] <= 0xf3 && (p[1] & 0xc0) == 0x80 &&
        (p[2] & 0xc0) == 0x80 && (p[3] & 0xc0) == 0x80) return 4;
    if (p[0] == 0xf4 && p[1] >= 0x80 && p[1] <= 0x8f &&
        (p[2] & 0xc0) == 0x80 && (p[3] & 0xc0) == 0x80) return 4;
    return 0;
}

static void json_string(const char *value) {
    putchar('"');
    const unsigned char *p = (const unsigned char *)value;
    while (*p) {
        switch (*p) {
            case '"': fputs("\\\"", stdout); p++; break;
            case '\\': fputs("\\\\", stdout); p++; break;
            case '\b': fputs("\\b", stdout); p++; break;
            case '\f': fputs("\\f", stdout); p++; break;
            case '\n': fputs("\\n", stdout); p++; break;
            case '\r': fputs("\\r", stdout); p++; break;
            case '\t': fputs("\\t", stdout); p++; break;
            default:
                if (*p < 0x20) {
                    printf("\\u%04x", *p);
                    p++;
                } else if (*p < 0x7f) {
                    putchar(*p++);
                } else {
                    size_t n = utf8_length(p);
                    if (n) {
                        fwrite(p, 1, n, stdout);
                        p += n;
                    } else {
                        printf("\\u%04x", *p);
                        p++;
                    }
                }
        }
    }
    putchar('"');
}

static void print_json(const char *source, const TokenList *tokens,
                       const Trace *trace, int accepted, const char *error) {
    size_t shifts = 0, reductions = 0, errors = 0;
    for (size_t i = 0; i < trace->count; i++) {
        shifts += trace->items[i].action == SHIFT;
        reductions += trace->items[i].action == REDUCE;
        errors += trace->items[i].action == ERROR;
    }
    fputs("{\"parser\":\"LALR\",\"input\":", stdout);
    json_string(source);
    fputs(",\"tokens\":[", stdout);
    for (size_t i = 0; i < tokens->count; i++) {
        if (i) putchar(',');
        fputs("{\"type\":", stdout); json_string(tokens->items[i].type);
        fputs(",\"lexeme\":", stdout); json_string(tokens->items[i].lexeme);
        putchar('}');
    }
    fputs("],\"result\":", stdout);
    json_string(accepted ? "ACCEPTED" : "SYNTAX ERROR");
    fputs(",\"error\":", stdout);
    if (accepted) fputs("null", stdout); else json_string(error);
    fputs(",\"steps\":[", stdout);
    for (size_t i = 0; i < trace->count; i++) {
        const TraceStep *step = &trace->items[i];
        if (i) putchar(',');
        printf("{\"step\":%zu,\"stack\":[", i);
        for (size_t j = 0; j < step->stack_count; j++) {
            if (j) putchar(',');
            json_string(step->stack[j]);
        }
        fputs("],\"remaining_input\":[", stdout);
        for (size_t j = step->input_index; j < tokens->count; j++) {
            if (j != step->input_index) putchar(',');
            json_string(tokens->items[j].lexeme);
        }
        if (step->input_index < tokens->count) putchar(',');
        json_string("$");
        fputs("],\"action\":", stdout); json_string(action_name(step->action));
        printf(",\"state\":%d,\"token\":", step->state);
        if (step->action == SHIFT && step->token_index >= 0 && (size_t)step->token_index < tokens->count) {
            const Token *token = &tokens->items[step->token_index];
            fputs("{\"type\":", stdout); json_string(token->type);
            fputs(",\"lexeme\":", stdout); json_string(token->lexeme);
            putchar('}');
        } else fputs("null", stdout);
        fputs(",\"production\":", stdout);
        if (step->action == REDUCE) json_string(productions[step->production].text);
        else fputs("null", stdout);
        fputs(",\"goto_state\":", stdout);
        if (step->action == REDUCE) printf("%d", step->goto_state);
        else fputs("null", stdout);
        putchar('}');
    }
    printf("],\"stats\":{\"token_count\":%zu,\"total_steps\":%zu,\"shifts\":%zu,\"reductions\":%zu,\"errors\":%zu}}\n",
           tokens->count, trace->count, shifts, reductions, errors);
}

static void free_trace(Trace *trace) {
    for (size_t i = 0; i < trace->count; i++) {
        for (size_t j = 0; j < trace->items[i].stack_count; j++) free(trace->items[i].stack[j]);
        free(trace->items[i].stack);
    }
    free(trace->items);
}

static int parse_trace_log(FILE *log, const TokenList *tokens, ParserStack *stack,
                           Trace *trace, size_t *consumed, int *eof_shift) {
    char line[2048];
    enum { NO_PENDING, PENDING_SHIFT, PENDING_REDUCE } pending = NO_PENDING;
    int pending_rule = 0;
    while (fgets(line, sizeof(line), log)) {
        if (strncmp(line, "Shifting token ", 15) == 0) {
            pending = PENDING_SHIFT;
        } else if (sscanf(line, "Reducing stack by rule %d", &pending_rule) == 1) {
            pending = PENDING_REDUCE;
        } else if (pending != NO_PENDING && strncmp(line, "Entering state ", 15) == 0) {
            int destination;
            if (sscanf(line + 15, "%d", &destination) != 1) return 0;
            if (pending == PENDING_SHIFT) {
                if (*consumed < tokens->count) {
                    int index = (int)*consumed;
                    if (!stack_push(stack, tokens->items[*consumed].type, destination)) return 0;
                    (*consumed)++;
                    if (!add_step(trace, SHIFT, destination, index, 0, -1, stack, *consumed)) return 0;
                } else {
                    if (!stack_push(stack, "$", destination)) return 0;
                    *eof_shift = 1;
                }
            } else {
                if (pending_rule < 1 || (size_t)pending_rule >= sizeof(productions) / sizeof(productions[0])) return 0;
                const Production *production = &productions[pending_rule];
                if (production->rhs_count > stack->count) return 0;
                for (size_t i = 0; i < production->rhs_count; i++) {
                    const char *actual = stack->symbols[stack->count - production->rhs_count + i];
                    if (strcmp(actual, production->rhs[i]) != 0) return 0;
                }
                stack_pop(stack, production->rhs_count);
                if (!stack_push(stack, production->lhs, destination)) return 0;
                if (!add_step(trace, REDUCE, destination, -1, pending_rule, destination, stack, *consumed)) return 0;
            }
            pending = NO_PENDING;
        }
    }
    return pending == NO_PENDING;
}

static char *read_all(FILE *stream, size_t *length) {
    size_t capacity = 4096;
    size_t used = 0;
    char *data = malloc(capacity + 1);
    if (!data) return NULL;
    for (;;) {
        if (used == capacity) {
            if (capacity > SIZE_MAX / 2) { free(data); return NULL; }
            capacity *= 2;
            char *larger = realloc(data, capacity + 1);
            if (!larger) { free(data); return NULL; }
            data = larger;
        }
        size_t n = fread(data + used, 1, capacity - used, stream);
        used += n;
        if (n == 0) {
            if (ferror(stream)) { free(data); return NULL; }
            break;
        }
    }
    data[used] = '\0';
    *length = used;
    return data;
}

static void free_stack(ParserStack *stack) {
    stack_pop(stack, stack->count);
    free(stack->symbols);
    free(stack->states);
}

static int run_json(void) {
    size_t source_length = 0;
    char *source = read_all(stdin, &source_length);
    if (!source) {
        fputs("parser: unable to read standard input\n", stderr);
        return 2;
    }
    TokenList tokens = {0};
    if (!tokenize(source, source_length, &tokens)) {
        fputs("parser: unable to tokenize input (out of memory or input too large)\n", stderr);
        free(source);
        free_tokens(&tokens);
        return 2;
    }
    YY_BUFFER_STATE parse_buffer = yy_scan_bytes(source, (int)source_length);
    FILE *trace_log = tmpfile();
    if (!parse_buffer || !trace_log) {
        fputs("parser: unable to initialize trace capture\n", stderr);
        if (parse_buffer) yy_delete_buffer(parse_buffer);
        if (trace_log) fclose(trace_log);
        free(source);
        free_tokens(&tokens);
        return 2;
    }

    ParserStack stack = {0};
    Trace trace = {0};
    stack.states = malloc(sizeof(*stack.states));
    if (!stack.states) {
        fputs("parser: out of memory\n", stderr);
        fclose(trace_log); yy_delete_buffer(parse_buffer); free(source); free_tokens(&tokens);
        return 2;
    }
    stack.states[0] = 0;
    if (!add_step(&trace, INIT, 0, -1, 0, -1, &stack, 0)) {
        fputs("parser: out of memory\n", stderr);
        free_stack(&stack); free_trace(&trace); fclose(trace_log); yy_delete_buffer(parse_buffer); free(source); free_tokens(&tokens);
        return 2;
    }

    int saved_stderr = dup(STDERR_FILENO);
    if (saved_stderr < 0 || dup2(fileno(trace_log), STDERR_FILENO) < 0) {
        fputs("parser: unable to capture parser trace\n", stderr);
        if (saved_stderr >= 0) close(saved_stderr);
        free_stack(&stack); free_trace(&trace); fclose(trace_log); yy_delete_buffer(parse_buffer); free(source); free_tokens(&tokens);
        return 2;
    }
    setlocale(LC_ALL, "C");
    yydebug = 1;
    json_mode = 1;
    parse_error[0] = '\0';
    int parse_result = yyparse();
    fflush(stderr);
    dup2(saved_stderr, STDERR_FILENO);
    close(saved_stderr);
    yydebug = 0;
    json_mode = 0;
    yy_delete_buffer(parse_buffer);

    int trace_ok = fseek(trace_log, 0, SEEK_SET) == 0;
    size_t consumed = 0;
    int eof_shift = 0;
    if (trace_ok) trace_ok = parse_trace_log(trace_log, &tokens, &stack, &trace, &consumed, &eof_shift);
    fclose(trace_log);
    int accepted = parse_result == 0 && trace_ok;
    if (accepted && !eof_shift) {
        if (!stack_push(&stack, "$", stack.states[stack.count])) accepted = 0;
    }
    if (!trace_ok) snprintf(parse_error, sizeof(parse_error), "Unable to interpret Bison parser trace");
    if (accepted) {
        if (!add_step(&trace, ACCEPT, stack.states[stack.count], -1, 0, -1, &stack, tokens.count)) accepted = 0;
    }
    if (!accepted) {
        if (consumed < tokens.count && strcmp(tokens.items[consumed].type, "INVALID") == 0)
            snprintf(parse_error, sizeof(parse_error), "Unexpected character '%s'", tokens.items[consumed].lexeme);
        else if (consumed < tokens.count)
            snprintf(parse_error, sizeof(parse_error), "Unexpected token %s ('%s')", tokens.items[consumed].type, tokens.items[consumed].lexeme);
        else snprintf(parse_error, sizeof(parse_error), "Syntax error at end of input");
        if (!add_step(&trace, ERROR, stack.states[stack.count], -1, 0, -1, &stack, consumed)) {
            fputs("parser: out of memory while recording error\n", stderr);
            free_stack(&stack); free_trace(&trace); free(source); free_tokens(&tokens);
            return 2;
        }
    }
    print_json(source, &tokens, &trace, accepted, parse_error);
    free_stack(&stack);
    free_trace(&trace);
    free(source);
    free_tokens(&tokens);
    return 0;
}

void yyerror(const char *message) {
    if (json_mode) {
        if (!parse_error[0]) snprintf(parse_error, sizeof(parse_error), "%s", message ? message : "Syntax error");
    } else {
        (void)message;
        printf("\nSyntax Error");
    }
}

static int print_table(void) {
    FILE *table = fopen("lalr_parser.output", "r");
    if (!table) {
        fprintf(stderr, "parser: lalr_parser.output not found; run `make` first\n");
        return 1;
    }
    int ch;
    while ((ch = fgetc(table)) != EOF) putchar(ch);
    int failed = ferror(table);
    fclose(table);
    return failed ? 1 : 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--json") == 0) return run_json();
    if (argc == 2 && strcmp(argv[1], "--table") == 0) return print_table();
    if (argc != 1) {
        fprintf(stderr, "Usage: %s [--json | --table]\n", argv[0]);
        return 2;
    }
    fputs("================  LEXICAL ANALYSIS  ================\n", stdout);
    int result = yyparse();
    fputs("\n================     PARSING    ================\n", stdout);
    fputs("Parser: LALR\n", stdout);
    printf("Result: %s\n", result == 0 ? "ACCEPTED" : "SYNTAX ERROR");
    return result;
}
