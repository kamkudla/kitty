// License: GPLv3 Copyright: 2022, Kovid Goyal, <kovid at kovidgoyal.net>

package utils

import (
	"crypto/rand"
	"encoding/base32"
	"fmt"
	"io/fs"
	not_rand "math/rand"
	"os"
	"os/exec"
	"os/user"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"

	"golang.org/x/sys/unix"
)

var Sep = string(os.PathSeparator)

func Expanduser(path string) string {
	if !strings.HasPrefix(path, "~") {
		return path
	}
	home, err := os.UserHomeDir()
	if err != nil {
		usr, err := user.Current()
		if err == nil {
			home = usr.HomeDir
		}
	}
	if err != nil || home == "" {
		return path
	}
	if path == "~" {
		return home
	}
	path = strings.ReplaceAll(path, Sep, "/")
	parts := strings.Split(path, "/")
	if parts[0] == "~" {
		parts[0] = home
	} else {
		uname := parts[0][1:]
		if uname != "" {
			u, err := user.Lookup(uname)
			if err == nil && u.HomeDir != "" {
				parts[0] = u.HomeDir
			}
		}
	}
	return strings.Join(parts, Sep)
}

func Abspath(path string) string {
	q, err := filepath.Abs(path)
	if err == nil {
		return q
	}
	return path
}

var KittyExe = (&Once[string]{Run: func() string {
	exe, err := os.Executable()
	if err == nil {
		return filepath.Join(filepath.Dir(exe), "kitty")
	}
	return ""
}}).Get

var ConfigDir = (&Once[string]{Run: func() (config_dir string) {
	if kcd := os.Getenv("KITTY_CONFIG_DIRECTORY"); kcd != "" {
		return Abspath(Expanduser(kcd))
	}
	var locations []string
	seen := Set[string]{}
	add := func(x string) {
		x = Abspath(Expanduser(x))
		if !seen.Has(x) {
			seen.Add(x)
			locations = append(locations, x)
		}
	}
	if xh := os.Getenv("XDG_CONFIG_HOME"); xh != "" {
		add(xh)
	}
	if dirs := os.Getenv("XDG_CONFIG_DIRS"); dirs != "" {
		for _, candidate := range strings.Split(dirs, ":") {
			add(candidate)
		}
	}
	add("~/.config")
	if runtime.GOOS == "darwin" {
		add("~/Library/Preferences")
	}
	for _, loc := range locations {
		if loc != "" {
			q := filepath.Join(loc, "kitty")
			if _, err := os.Stat(filepath.Join(q, "kitty.conf")); err == nil {
				config_dir = q
				return
			}
		}
	}
	config_dir = os.Getenv("XDG_CONFIG_HOME")
	if config_dir == "" {
		config_dir = "~/.config"
	}
	config_dir = filepath.Join(Expanduser(config_dir), "kitty")
	return
}}).Get

var CacheDir = (&Once[string]{Run: func() (cache_dir string) {
	candidate := ""
	if edir := os.Getenv("KITTY_CACHE_DIRECTORY"); edir != "" {
		candidate = Abspath(Expanduser(edir))
	} else if runtime.GOOS == "darwin" {
		candidate = Expanduser("~/Library/Caches/kitty")
	} else {
		candidate = os.Getenv("XDG_CACHE_HOME")
		if candidate == "" {
			candidate = "~/.cache"
		}
		candidate = filepath.Join(Expanduser(candidate), "kitty")
	}
	os.MkdirAll(candidate, 0o755)
	return candidate
}}).Get

func macos_user_cache_dir() string {
	// Sadly Go does not provide confstr() so we use this hack. We could
	// Note that given a user generateduid and uid we can derive this by using
	// the algorithm at https://github.com/ydkhatri/MacForensics/blob/master/darwin_path_generator.py
	// but I cant find a good way to get the generateduid. Requires calling dscl in which case we might as well call getconf
	// The data is in /var/db/dslocal/nodes/Default/users/<username>.plist but it needs root
	matches, err := filepath.Glob("/private/var/folders/*/*/C")
	if err == nil {
		for _, m := range matches {
			s, err := os.Stat(m)
			if err == nil {
				if stat, ok := s.Sys().(unix.Stat_t); ok && s.IsDir() && int(stat.Uid) == os.Geteuid() && s.Mode().Perm() == 0o700 && unix.Access(m, unix.X_OK|unix.W_OK|unix.R_OK) == nil {
					return m
				}
			}
		}
	}
	out, err := exec.Command("/usr/bin/getconf", "DARWIN_USER_CACHE_DIR").Output()
	if err == nil {
		return strings.TrimSpace(UnsafeBytesToString(out))
	}
	return ""
}

var RuntimeDir = (&Once[string]{Run: func() (runtime_dir string) {
	var candidate string
	if q := os.Getenv("KITTY_RUNTIME_DIRECTORY"); q != "" {
		candidate = q
	} else if runtime.GOOS == "darwin" {
		candidate = macos_user_cache_dir()
	} else if q := os.Getenv("XDG_RUNTIME_DIR"); q != "" {
		candidate = q
	}
	candidate = strings.TrimRight(candidate, "/")
	if candidate == "" {
		q := fmt.Sprintf("/run/user/%d", os.Geteuid())
		if s, err := os.Stat(q); err == nil && s.IsDir() && unix.Access(q, unix.X_OK|unix.R_OK|unix.W_OK) == nil {
			candidate = q
		} else {
			candidate = filepath.Join(CacheDir(), "run")
		}
	}
	os.MkdirAll(candidate, 0o700)
	if s, err := os.Stat(candidate); err == nil && s.Mode().Perm() != 0o700 {
		os.Chmod(candidate, 0o700)
	}
	return candidate
}}).Get

type Walk_callback func(path, abspath string, d fs.DirEntry, err error) error

func transform_symlink(path string) string {
	if q, err := filepath.EvalSymlinks(path); err == nil {
		return q
	}
	return path
}

func needs_symlink_recurse(path string, d fs.DirEntry) bool {
	if d.Type()&os.ModeSymlink == os.ModeSymlink {
		if s, serr := os.Stat(path); serr == nil && s.IsDir() {
			return true
		}
	}
	return false
}

type transformed_walker struct {
	seen               map[string]bool
	real_callback      Walk_callback
	transform_func     func(string) string
	needs_recurse_func func(string, fs.DirEntry) bool
}

func (self *transformed_walker) walk(dirpath string) error {
	resolved_path := self.transform_func(dirpath)
	if self.seen[resolved_path] {
		return nil
	}
	self.seen[resolved_path] = true

	c := func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			// Happens if ReadDir on d failed, skip it in that case
			return fs.SkipDir
		}
		rpath, err := filepath.Rel(resolved_path, path)
		if err != nil {
			return err
		}
		// we cant use filepath.Join here as it calls Clean() which can alter dirpath if it contains .. or . etc.
		path_based_on_original_dir := dirpath
		if !strings.HasSuffix(dirpath, Sep) && dirpath != "" {
			path_based_on_original_dir += Sep
		}
		path_based_on_original_dir += rpath
		if self.needs_recurse_func(path, d) {
			err = self.walk(path_based_on_original_dir)
		} else {
			err = self.real_callback(path_based_on_original_dir, path, d, err)
		}
		return err
	}

	return filepath.WalkDir(resolved_path, c)
}

// Walk, recursing into symlinks that point to directories. Ignores directories
// that could not be read.
func WalkWithSymlink(dirpath string, callback Walk_callback, transformers ...func(string) string) error {

	transform := func(path string) string {
		for _, t := range transformers {
			path = t(path)
		}
		return transform_symlink(path)
	}
	sw := transformed_walker{
		seen: make(map[string]bool), real_callback: callback, transform_func: transform, needs_recurse_func: needs_symlink_recurse}
	return sw.walk(dirpath)
}

func RandomFilename() string {
	b := []byte{0, 0, 0, 0, 0, 0, 0, 0}
	_, err := rand.Read(b)
	if err != nil {
		return strconv.FormatUint(uint64(not_rand.Uint32()), 16)
	}
	return base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(b)

}
