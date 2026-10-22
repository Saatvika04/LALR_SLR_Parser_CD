#define _POSIX_C_SOURCE 200809L
#include <lalr_parser.tab.h>
#include "slr_grammar.generated.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct yy_buffer_state *YY_BUFFER_STATE;
extern YY_BUFFER_STATE yy_scan_bytes(const char *bytes, int length);
extern void yy_delete_buffer(YY_BUFFER_STATE buffer);
extern int yylex(void);
extern char *yytext;

#define MAX_STATES 256
#define MAX_STACK 65536
typedef struct { unsigned char item[SLR_PRODUCTION_COUNT][SLR_MAX_RHS + 1]; } State;
typedef struct { int kind; int value; } Action;
typedef struct { char *type; char *lexeme; int symbol; } Token;
typedef struct { Token *data; size_t count, capacity; } Tokens;
enum { NO_ACTION, SHIFT_ACTION, REDUCE_ACTION, ACCEPT_ACTION };
enum { INIT_STEP, SHIFT_STEP, REDUCE_STEP, ACCEPT_STEP, ERROR_STEP };
typedef struct {
    int action, state, token_index, production, goto_state;
    size_t input_index, stack_count;
    int *symbols, *states;
} Step;
typedef struct { Step *data; size_t count, capacity; } Steps;

static State states[MAX_STATES];
static int state_count;
static int transitions[MAX_STATES][SLR_SYMBOL_COUNT];
static Action actions[MAX_STATES][SLR_TERMINAL_COUNT + 1];
static int gotos[MAX_STATES][SLR_NONTERMINAL_COUNT];
static uint64_t first_sets[SLR_SYMBOL_COUNT];
static uint64_t follow_sets[SLR_NONTERMINAL_COUNT];
static int automaton_ready;

static char *copy_string(const char *text) {
    size_t n = strlen(text) + 1;
    char *copy = malloc(n);
    if (copy) memcpy(copy, text, n);
    return copy;
}

static void json_string(const char *text) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)text; *p; p++) {
        switch (*p) {
            case '"': fputs("\\\"", stdout); break;
            case '\\': fputs("\\\\", stdout); break;
            case '\n': fputs("\\n", stdout); break;
            case '\r': fputs("\\r", stdout); break;
            case '\t': fputs("\\t", stdout); break;
            case '\b': fputs("\\b", stdout); break;
            case '\f': fputs("\\f", stdout); break;
            default:
                if (*p < 0x20) printf("\\u%04x", *p);
                else putchar(*p);
        }
    }
    putchar('"');
}

static int is_nonterminal(int symbol) {
    return symbol >= SLR_TERMINAL_COUNT + 1 && symbol < SLR_SYMBOL_COUNT;
}

static int nt_index(int symbol) { return symbol - (SLR_TERMINAL_COUNT + 1); }

static int closure(State *state) {
    int changed;
    do {
        changed = 0;
        for (int p = 0; p < SLR_PRODUCTION_COUNT; p++) {
            for (unsigned dot = 0; dot < slr_productions[p].rhs_count; dot++) {
                if (!state->item[p][dot]) continue;
                int symbol = slr_productions[p].rhs[dot];
                if (!is_nonterminal(symbol)) continue;
                for (int q = 0; q < SLR_PRODUCTION_COUNT; q++) {
                    if (slr_productions[q].lhs == symbol && !state->item[q][0]) {
                        state->item[q][0] = 1;
                        changed = 1;
                    }
                }
            }
        }
    } while (changed);
    return 1;
}

static int same_state(const State *a, const State *b) {
    return memcmp(a, b, sizeof(*a)) == 0;
}

static int add_state(const State *candidate) {
    for (int i = 0; i < state_count; i++) if (same_state(&states[i], candidate)) return i;
    if (state_count >= MAX_STATES) return -1;
    states[state_count] = *candidate;
    return state_count++;
}

static int build_states(void) {
    memset(states, 0, sizeof(states));
    memset(transitions, 0xff, sizeof(transitions));
    memset(actions, 0, sizeof(actions));
    memset(gotos, 0xff, sizeof(gotos));
    memset(first_sets, 0, sizeof(first_sets));
    memset(follow_sets, 0, sizeof(follow_sets));
    state_count = 0;
    State start = {0};
    start.item[0][0] = 1;
    closure(&start);
    if (add_state(&start) < 0) return 0;

    for (int s = 0; s < state_count; s++) {
        for (int symbol = 0; symbol < SLR_SYMBOL_COUNT; symbol++) {
            if (symbol == SLR_EOF) continue;
            State next = {0};
            for (int p = 0; p < SLR_PRODUCTION_COUNT; p++) {
                for (unsigned dot = 0; dot < slr_productions[p].rhs_count; dot++) {
                    if (states[s].item[p][dot] && slr_productions[p].rhs[dot] == symbol)
                        next.item[p][dot + 1] = 1;
                }
            }
            int has_items = 0;
            for (int p = 0; p < SLR_PRODUCTION_COUNT && !has_items; p++)
                for (unsigned d = 0; d <= slr_productions[p].rhs_count; d++)
                    if (next.item[p][d]) { has_items = 1; break; }
            if (!has_items) continue;
            closure(&next);
            int destination = add_state(&next);
            if (destination < 0) return 0;
            transitions[s][symbol] = destination;
        }
    }
    return 1;
}

static void compute_first_follow(void) {
    for (int t = 0; t < SLR_TERMINAL_COUNT; t++) first_sets[t] = UINT64_C(1) << t;
    int changed;
    do {
        changed = 0;
        for (int p = 0; p < SLR_PRODUCTION_COUNT; p++) {
            int lhs = slr_productions[p].lhs;
            if (!slr_productions[p].rhs_count) continue;
            int sym = slr_productions[p].rhs[0];
            uint64_t before = first_sets[lhs];
            first_sets[lhs] |= first_sets[sym];
            if (before != first_sets[lhs]) changed = 1;
        }
    } while (changed);

    follow_sets[nt_index(G_S_PRIME)] = UINT64_C(1) << SLR_EOF;
    do {
        changed = 0;
        for (int p = 0; p < SLR_PRODUCTION_COUNT; p++) {
            int lhs_index = nt_index(slr_productions[p].lhs);
            for (unsigned i = 0; i < slr_productions[p].rhs_count; i++) {
                int symbol = slr_productions[p].rhs[i];
                if (!is_nonterminal(symbol)) continue;
                uint64_t addition = 0;
                if (i + 1 < slr_productions[p].rhs_count) {
                    addition = first_sets[slr_productions[p].rhs[i + 1]];
                } else {
                    addition = follow_sets[lhs_index];
                }
                int index = nt_index(symbol);
                uint64_t before = follow_sets[index];
                follow_sets[index] |= addition;
                if (before != follow_sets[index]) changed = 1;
            }
        }
    } while (changed);
}

static int put_action(int state, int terminal, int kind, int value) {
    Action *slot = &actions[state][terminal];
    if (slot->kind && (slot->kind != kind || slot->value != value)) return 0;
    slot->kind = kind;
    slot->value = value;
    return 1;
}

static int build_automaton(void) {
    if (!build_states()) return 0;
    compute_first_follow();
    for (int s = 0; s < state_count; s++) {
        for (int p = 0; p < SLR_PRODUCTION_COUNT; p++) {
            const SlrProduction *production = &slr_productions[p];
            for (unsigned dot = 0; dot <= production->rhs_count; dot++) {
                if (!states[s].item[p][dot]) continue;
                if (dot < production->rhs_count) {
                    int symbol = production->rhs[dot];
                    int destination = transitions[s][symbol];
                    if (destination < 0) return 0;
                    if (symbol < SLR_TERMINAL_COUNT) {
                        if (!put_action(s, symbol, SHIFT_ACTION, destination)) return 0;
                    } else if (is_nonterminal(symbol)) {
                        gotos[s][nt_index(symbol)] = destination;
                    }
                } else if (p == 0) {
                    if (!put_action(s, SLR_EOF, ACCEPT_ACTION, 0)) return 0;
                } else {
                    uint64_t follows = follow_sets[nt_index(production->lhs)];
                    for (int t = 0; t <= SLR_EOF; t++)
                        if ((follows & (UINT64_C(1) << t)) && !put_action(s, t, REDUCE_ACTION, p)) return 0;
                }
            }
        }
    }
    automaton_ready = 1;
    return 1;
}

static int map_token(int token) {
    switch (token) {
        case ID: return G_ID;
        case NUM: return G_NUM;
        case ASSIGN: return G_ASSIGN;
        case SEMICOLON: return G_SEMICOLON;
        case PLUS: return G_PLUS;
        case MINUS: return G_MINUS;
        case MULT: return G_MULT;
        case DIV: return G_DIV;
        case LPAREN: return G_LPAREN;
        case RPAREN: return G_RPAREN;
        default: return -1;
    }
}

static const char *token_name(int token) {
    switch (token) {
        case ID: return "ID"; case NUM: return "NUM"; case ASSIGN: return "ASSIGN";
        case SEMICOLON: return "SEMICOLON"; case PLUS: return "PLUS"; case MINUS: return "MINUS";
        case MULT: return "MULT"; case DIV: return "DIV"; case LPAREN: return "LPAREN";
        case RPAREN: return "RPAREN"; case IF: return "IF"; case ELSE: return "ELSE";
        case LT: return "LT"; case GT: return "GT"; case LE: return "LE"; case GE: return "GE";
        case EQ: return "EQ"; case NE: return "NE"; case INVALID: return "INVALID";
        default: return "UNKNOWN";
    }
}

static int append_token(Tokens *tokens, int token, const char *lexeme) {
    if (tokens->count == tokens->capacity) {
        size_t capacity = tokens->capacity ? tokens->capacity * 2 : 32;
        Token *larger = realloc(tokens->data, capacity * sizeof(*larger));
        if (!larger) return 0;
        tokens->data = larger;
        tokens->capacity = capacity;
    }
    Token *item = &tokens->data[tokens->count];
    item->type = copy_string(token_name(token));
    item->lexeme = copy_string(lexeme);
    item->symbol = map_token(token);
    if (!item->type || !item->lexeme) return 0;
    tokens->count++;
    return 1;
}

static void free_tokens(Tokens *tokens) {
    for (size_t i = 0; i < tokens->count; i++) { free(tokens->data[i].type); free(tokens->data[i].lexeme); }
    free(tokens->data);
    tokens->data = NULL;
    tokens->count = tokens->capacity = 0;
}

static int lex_source(const char *source, size_t length, Tokens *tokens, char *error, size_t error_size) {
    if (length > 2147483647U) return 0;
    YY_BUFFER_STATE buffer = yy_scan_bytes(source, (int)length);
    if (!buffer) return 0;
    int token, ok = 1;
    while ((token = yylex()) != 0) {
        if (token == INVALID) {
            snprintf(error, error_size, "Unexpected character '%s'", yytext);
            free_tokens(tokens);
            break;
        }
        if (!append_token(tokens, token, yytext)) { ok = 0; break; }
    }
    yy_delete_buffer(buffer);
    return ok;
}

static int add_step(Steps *steps, int action, int state, int token_index, int production,
                    int goto_state, const int *symbols, const int *state_stack,
                    size_t stack_count, size_t input_index) {
    if (steps->count == steps->capacity) {
        size_t capacity = steps->capacity ? steps->capacity * 2 : 32;
        Step *larger = realloc(steps->data, capacity * sizeof(*larger));
        if (!larger) return 0;
        steps->data = larger; steps->capacity = capacity;
    }
    Step *step = &steps->data[steps->count];
    memset(step, 0, sizeof(*step));
    step->action = action; step->state = state; step->token_index = token_index;
    step->production = production; step->goto_state = goto_state;
    step->input_index = input_index; step->stack_count = stack_count;
    step->symbols = malloc((stack_count ? stack_count : 1) * sizeof(*step->symbols));
    step->states = malloc((stack_count + 1) * sizeof(*step->states));
    if (!step->symbols || !step->states) { free(step->symbols); free(step->states); return 0; }
    if (stack_count) memcpy(step->symbols, symbols, stack_count * sizeof(*symbols));
    memcpy(step->states, state_stack, (stack_count + 1) * sizeof(*state_stack));
    steps->count++;
    return 1;
}

static void free_steps(Steps *steps) {
    for (size_t i = 0; i < steps->count; i++) { free(steps->data[i].symbols); free(steps->data[i].states); }
    free(steps->data);
}

static const char *step_name(int action) {
    static const char *names[] = {"INIT", "SHIFT", "REDUCE", "ACCEPT", "ERROR"};
    return names[action];
}

static int parse_input(const char *source, size_t source_length) {
    Tokens tokens = {0}; Steps steps = {0}; char error[512] = "";
    int lexical_ok = lex_source(source, source_length, &tokens, error, sizeof(error));
    if (!lexical_ok) {
        fputs("slr_parser: unable to tokenize input\n", stderr);
        free_tokens(&tokens); return 2;
    }
    if (!error[0] && !automaton_ready && !build_automaton()) {
        fputs("slr_parser: unable to construct conflict-free SLR table\n", stderr);
        free_tokens(&tokens); return 2;
    }
    if (error[0]) {
        fputs("{\"parser\":\"SLR\",\"input\":", stdout); json_string(source);
        fputs(",\"tokens\":[],\"result\":\"SYNTAX ERROR\",\"error\":", stdout); json_string(error);
        fputs(",\"steps\":[],\"stats\":{\"token_count\":0,\"total_steps\":0,\"shifts\":0,\"reductions\":0,\"errors\":1}}\n", stdout);
        free_tokens(&tokens); return 0;
    }

    int *symbols = calloc(MAX_STACK, sizeof(*symbols));
    int *state_stack = calloc(MAX_STACK + 1, sizeof(*state_stack));
    if (!symbols || !state_stack) { free(symbols); free(state_stack); free_tokens(&tokens); return 2; }
    size_t stack_count = 0, cursor = 0, shifts = 0, reductions = 0;
    int result = 0;
    if (!add_step(&steps, INIT_STEP, 0, -1, -1, -1, symbols, state_stack, stack_count, cursor)) result = 2;
    while (!result) {
        if (cursor > tokens.count || stack_count >= MAX_STACK) { result = 2; break; }
        int lookahead = cursor < tokens.count ? tokens.data[cursor].symbol : SLR_EOF;
        Action action = lookahead < 0 ? (Action){NO_ACTION, 0} : actions[state_stack[stack_count]][lookahead];
        if (action.kind == SHIFT_ACTION) {
            symbols[stack_count] = lookahead; stack_count++;
            state_stack[stack_count] = action.value; cursor++; shifts++;
            if (!add_step(&steps, SHIFT_STEP, action.value, (int)cursor - 1, -1, -1,
                          symbols, state_stack, stack_count, cursor)) result = 2;
        } else if (action.kind == REDUCE_ACTION) {
            const SlrProduction *production = &slr_productions[action.value];
            if (production->rhs_count > stack_count) { result = 2; break; }
            stack_count -= production->rhs_count;
            int destination = gotos[state_stack[stack_count]][nt_index(production->lhs)];
            if (destination < 0 || stack_count >= MAX_STACK) { result = 2; break; }
            symbols[stack_count] = production->lhs; stack_count++;
            state_stack[stack_count] = destination; reductions++;
            if (!add_step(&steps, REDUCE_STEP, destination, -1, action.value, destination,
                          symbols, state_stack, stack_count, cursor)) result = 2;
        } else if (action.kind == ACCEPT_ACTION) {
            if (!add_step(&steps, ACCEPT_STEP, state_stack[stack_count], -1, -1, -1,
                          symbols, state_stack, stack_count, cursor)) result = 2;
            break;
        } else {
            const char *name = lookahead == SLR_EOF ? "$" : tokens.data[cursor].type;
            if (lookahead == SLR_EOF) snprintf(error, sizeof(error), "Unexpected token %s (lexeme '$')", name);
            else snprintf(error, sizeof(error), "Unexpected token %s (lexeme '%s')", name, tokens.data[cursor].lexeme);
            if (!add_step(&steps, ERROR_STEP, state_stack[stack_count], -1, -1, -1,
                          symbols, state_stack, stack_count, cursor)) result = 2;
            break;
        }
    }
    if (result == 2) {
        fputs("slr_parser: parsing failed due to an internal error or resource limit\n", stderr);
    } else {
        int accepted = steps.count && steps.data[steps.count - 1].action == ACCEPT_STEP;
        size_t errors = accepted ? 0 : 1;
        fputs("{\"parser\":\"SLR\",\"input\":", stdout); json_string(source);
        fputs(",\"tokens\":[", stdout);
        for (size_t i = 0; i < tokens.count; i++) {
            if (i) putchar(',');
            fputs("{\"type\":", stdout); json_string(tokens.data[i].type);
            fputs(",\"lexeme\":", stdout); json_string(tokens.data[i].lexeme); putchar('}');
        }
        fputs("],\"result\":", stdout); json_string(accepted ? "ACCEPTED" : "SYNTAX ERROR");
        fputs(",\"error\":", stdout); if (accepted) fputs("null", stdout); else json_string(error);
        fputs(",\"steps\":[", stdout);
        for (size_t i = 0; i < steps.count; i++) {
            Step *step = &steps.data[i]; if (i) putchar(',');
            printf("{\"step\":%zu,\"stack\":[", i);
            for (size_t j = 0; j <= step->stack_count * 2; j++) {
                if (j) putchar(',');
                if (j % 2 == 0) printf("\"%d\"", step->states[j / 2]);
                else json_string(slr_symbol_names[step->symbols[j / 2]]);
            }
            fputs("],\"remaining_input\":[", stdout);
            for (size_t j = step->input_index; j < tokens.count; j++) {
                if (j != step->input_index) putchar(',');
                json_string(tokens.data[j].lexeme);
            }
            if (step->input_index < tokens.count) putchar(',');
            json_string("$");
            fputs("],\"action\":", stdout); json_string(step_name(step->action));
            printf(",\"state\":%d,\"token\":", step->state);
            if (step->action == SHIFT_STEP) {
                Token *token = &tokens.data[step->token_index]; fputs("{\"type\":", stdout);
                json_string(token->type); fputs(",\"lexeme\":", stdout); json_string(token->lexeme); putchar('}');
            } else fputs("null", stdout);
            fputs(",\"production\":", stdout);
            if (step->action == REDUCE_STEP) json_string(slr_productions[step->production].text); else fputs("null", stdout);
            fputs(",\"goto_state\":", stdout);
            if (step->action == REDUCE_STEP) printf("%d", step->goto_state); else fputs("null", stdout);
            putchar('}');
        }
        printf("],\"stats\":{\"token_count\":%zu,\"total_steps\":%zu,\"shifts\":%zu,\"reductions\":%zu,\"errors\":%zu}}\n",
               tokens.count, steps.count, shifts, reductions, errors);
    }
    free(symbols); free(state_stack); free_tokens(&tokens); free_steps(&steps);
    return result;
}

static int compare_strings(const void *a, const void *b) {
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}

static void sort_symbol_ids(int *symbols, size_t count) {
    for (size_t i = 1; i < count; i++) {
        int value = symbols[i];
        size_t j = i;
        while (j && strcmp(slr_symbol_names[symbols[j - 1]], slr_symbol_names[value]) > 0) {
            symbols[j] = symbols[j - 1];
            j--;
        }
        symbols[j] = value;
    }
}

static char *format_item(int production, unsigned dot) {
    const SlrProduction *p = &slr_productions[production];
    size_t size = strlen(slr_symbol_names[p->lhs]) + 5;
    for (unsigned i = 0; i < p->rhs_count; i++) size += strlen(slr_symbol_names[p->rhs[i]]) + 1;
    char *text = malloc(size + 1); if (!text) return NULL;
    size_t used = (size_t)snprintf(text, size + 1, "%s ->", slr_symbol_names[p->lhs]);
    for (unsigned i = 0; i <= p->rhs_count; i++) {
        if (i == dot) used += (size_t)snprintf(text + used, size + 1 - used, " .");
        if (i < p->rhs_count) used += (size_t)snprintf(text + used, size + 1 - used, " %s", slr_symbol_names[p->rhs[i]]);
    }
    return text;
}

static void print_set(uint64_t set) {
    int members[SLR_TERMINAL_COUNT + 1]; size_t count = 0;
    for (int t = 0; t <= SLR_EOF; t++) if (set & (UINT64_C(1) << t)) members[count++] = t;
    sort_symbol_ids(members, count);
    putchar('[');
    for (size_t i = 0; i < count; i++) { if (i) putchar(','); json_string(slr_symbol_names[members[i]]); }
    putchar(']');
}

static void print_automaton(void) {
    fputs("{\"parser\":\"SLR\",\"terminals\":[", stdout);
    for (int t = 0; t < SLR_TERMINAL_COUNT; t++) { if (t) putchar(','); json_string(slr_symbol_names[t]); }
    fputs("],\"nonterminals\":[", stdout);
    for (int n = 1; n < SLR_NONTERMINAL_COUNT; n++) { if (n > 1) putchar(','); json_string(slr_nonterminal_names[n]); }
    fputs("],\"grammar\":[", stdout);
    for (int p = 0; p < SLR_PRODUCTION_COUNT; p++) {
        if (p) putchar(',');
        char text[256]; snprintf(text, sizeof(text), "%s → %s", slr_symbol_names[slr_productions[p].lhs], slr_productions[p].text + strlen(slr_symbol_names[slr_productions[p].lhs]) + 4);
        json_string(text);
    }
    fputs("],\"conflicts\":[],\"first\":{", stdout);
    for (int n = 0; n < SLR_NONTERMINAL_COUNT; n++) {
        if (n) putchar(',');
        json_string(slr_nonterminal_names[n]); putchar(':');
        print_set(first_sets[SLR_TERMINAL_COUNT + 1 + n]);
    }
    fputs("},\"follow\":{", stdout);
    for (int n = 0; n < SLR_NONTERMINAL_COUNT; n++) {
        if (n) putchar(',');
        json_string(slr_nonterminal_names[n]); putchar(':'); print_set(follow_sets[n]);
    }
    fputs("},\"states\":[", stdout);
    for (int s = 0; s < state_count; s++) {
        if (s) putchar(',');
        printf("{\"id\":%d,\"items\":[", s);
        char *items[SLR_PRODUCTION_COUNT * (SLR_MAX_RHS + 1)]; size_t item_count = 0;
        for (int p = 0; p < SLR_PRODUCTION_COUNT; p++)
            for (unsigned d = 0; d <= slr_productions[p].rhs_count; d++)
                if (states[s].item[p][d]) items[item_count++] = format_item(p, d);
        qsort(items, item_count, sizeof(*items), compare_strings);
        for (size_t i = 0; i < item_count; i++) { if (i) putchar(','); json_string(items[i]); free(items[i]); }
        fputs("],\"actions\":[", stdout); int comma = 0;
        int action_symbols[SLR_TERMINAL_COUNT + 1]; size_t action_count = 0;
        for (int t = 0; t <= SLR_EOF; t++) if (actions[s][t].kind) action_symbols[action_count++] = t;
        sort_symbol_ids(action_symbols, action_count);
        for (size_t action_index = 0; action_index < action_count; action_index++) {
            int t = action_symbols[action_index];
            Action a = actions[s][t]; if (comma++) putchar(',');
            fputs("{\"symbol\":", stdout); json_string(slr_symbol_names[t]);
            if (a.kind == SHIFT_ACTION) printf(",\"action\":\"shift\",\"to\":%d}", a.value);
            else if (a.kind == REDUCE_ACTION) { fputs(",\"action\":\"reduce\",\"production\":", stdout); json_string(slr_productions[a.value].text); printf(",\"production_index\":%d}", a.value); }
            else fputs(",\"action\":\"accept\"}", stdout);
        }
        fputs("],\"gotos\":[", stdout); comma = 0;
        int goto_indices[SLR_NONTERMINAL_COUNT]; size_t goto_count = 0;
        for (int n = 1; n < SLR_NONTERMINAL_COUNT; n++) if (gotos[s][n] >= 0) goto_indices[goto_count++] = n;
        for (size_t i = 1; i < goto_count; i++) {
            int value = goto_indices[i]; size_t j = i;
            while (j && strcmp(slr_nonterminal_names[goto_indices[j - 1]], slr_nonterminal_names[value]) > 0) {
                goto_indices[j] = goto_indices[j - 1]; j--;
            }
            goto_indices[j] = value;
        }
        for (size_t goto_index = 0; goto_index < goto_count; goto_index++) {
            int n = goto_indices[goto_index];
            if (comma++) putchar(',');
            fputs("{\"symbol\":", stdout); json_string(slr_nonterminal_names[n]);
            printf(",\"to\":%d}", gotos[s][n]);
        }
        fputs("]}", stdout);
    }
    fputs("]}\n", stdout);
}

static char *read_all(size_t *length) {
    size_t capacity = 4096, used = 0; char *data = malloc(capacity + 1);
    if (!data) return NULL;
    for (;;) {
        if (used == capacity) { capacity *= 2; char *larger = realloc(data, capacity + 1); if (!larger) { free(data); return NULL; } data = larger; }
        size_t count = fread(data + used, 1, capacity - used, stdin); used += count;
        if (!count) { if (ferror(stdin)) { free(data); return NULL; } break; }
    }
    data[used] = '\0'; *length = used; return data;
}

int main(int argc, char **argv) {
    if (!build_automaton()) { fputs("slr_parser: SLR table construction failed or grammar is not SLR(1)\n", stderr); return 2; }
    if (argc == 2 && strcmp(argv[1], "--automaton") == 0) { print_automaton(); return 0; }
    if (argc == 2 && strcmp(argv[1], "--json") == 0) {
        size_t length; char *source = read_all(&length); if (!source) return 2;
        int result = parse_input(source, length); free(source); return result;
    }
    if (argc != 1) { fprintf(stderr, "Usage: %s [--json | --automaton]\n", argv[0]); return 2; }
    size_t length; char *source = read_all(&length); if (!source) return 2;
    int result = parse_input(source, length); free(source); return result;
}
