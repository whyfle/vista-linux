# ~/.bashrc — Vista Linux default shell configuration

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# ── History ──────────────────────────────────────────────────────
HISTCONTROL=ignoreboth
HISTSIZE=5000
HISTFILESIZE=10000
shopt -s histappend

# ── Shell options ────────────────────────────────────────────────
shopt -s checkwinsize
shopt -s globstar 2>/dev/null
shopt -s cdspell

# ── Prompt ───────────────────────────────────────────────────────
# Purple "vista" tag + green user@host + blue directory
PS1='\[\033[1;35m\][vista]\[\033[0m\] \[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '

# ── Colour support ──────────────────────────────────────────────
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# ── Standard aliases ────────────────────────────────────────────
alias ll='ls -alFh'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'

# ── Vista aliases ────────────────────────────────────────────────
alias vi='vista install'
alias vs='vista search'
alias vr='vista remove'
alias vu='vista update'
alias vinfo='vista sys-info'
alias fetch='neofetch'

# ── Custom Fetch on interactive login ────────────────────────────
if command -v neofetch >/dev/null 2>&1; then
    neofetch
elif [ -f /usr/share/vista/vista-ascii.txt ]; then
    cat /usr/share/vista/vista-ascii.txt
fi

