#import <Cocoa/Cocoa.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#include <mach-o/dyld.h>
#include <libgen.h>
#include <unistd.h>
#include <stdlib.h>

static NSString *RuntimeBinaryPath(void) {
    char path[4096];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) != 0) {
        return nil;
    }
    char *copy = strdup(path);
    if (!copy) {
        return nil;
    }
    char *dir = dirname(copy);
    NSString *runtime = [[NSString stringWithUTF8String:dir]
        stringByAppendingPathComponent:@"../Resources/runtime/__BINARY__"];
    free(copy);
    return [[runtime stringByStandardizingPath] stringByResolvingSymlinksInPath];
}

static BOOL PathLooksLikePDF(NSString *path) {
    return path.length > 0 && [[path.pathExtension lowercaseString] isEqualToString:@"pdf"];
}

static void LaunchPeerFold(NSString *pdfPath) {
    NSString *runtime = RuntimeBinaryPath();
    if (!runtime || ![[NSFileManager defaultManager] isExecutableFileAtPath:runtime]) {
        fputs("PeerFold runtime not found.\n", stderr);
        exit(1);
    }
    const char *run = runtime.fileSystemRepresentation;
    if (pdfPath.length > 0) {
        execl(run, run, pdfPath.fileSystemRepresentation, (char *)NULL);
    } else {
        execl(run, run, (char *)NULL);
    }
    perror("execl");
    exit(1);
}

@interface AppDelegate : NSObject <NSApplicationDelegate>
@property (nonatomic, assign) BOOL opened;
@end

@implementation AppDelegate

- (BOOL)application:(NSApplication *)application openFile:(NSString *)filename {
    if (!PathLooksLikePDF(filename)) {
        return NO;
    }
    self.opened = YES;
    LaunchPeerFold(filename);
    return YES;
}

- (void)application:(NSApplication *)application openFiles:(NSArray<NSString *> *)filenames {
    for (NSString *filename in filenames) {
        if (PathLooksLikePDF(filename)) {
            self.opened = YES;
            LaunchPeerFold(filename);
            return;
        }
    }
}

- (void)promptForPDF {
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.allowedContentTypes = @[UTTypePDF];
    panel.canChooseFiles = YES;
    panel.canChooseDirectories = NO;
    panel.allowsMultipleSelection = NO;
    panel.prompt = @"Open";
    panel.message = @"Select a PDF to review";
    [panel beginWithCompletionHandler:^(NSModalResponse result) {
        if (result == NSModalResponseOK) {
            LaunchPeerFold(panel.URL.path);
        }
        [NSApp terminate:nil];
    }];
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    NSArray<NSString *> *args = [[NSProcessInfo processInfo] arguments];
    for (NSUInteger i = 1; i < args.count; i++) {
        NSString *arg = [args objectAtIndex:i];
        if (PathLooksLikePDF(arg)) {
            self.opened = YES;
            LaunchPeerFold(arg);
            return;
        }
    }

    __weak AppDelegate *weakSelf = self;
    dispatch_after(
        dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.2 * NSEC_PER_SEC)),
        dispatch_get_main_queue(),
        ^{
            if (!weakSelf.opened) {
                [weakSelf promptForPDF];
            }
        });
}

@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        if (argc > 1 && PathLooksLikePDF([NSString stringWithUTF8String:argv[1]])) {
            LaunchPeerFold([NSString stringWithUTF8String:argv[1]]);
        }

        NSApplication *app = [NSApplication sharedApplication];
        AppDelegate *delegate = [[AppDelegate alloc] init];
        app.delegate = delegate;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        [app activateIgnoringOtherApps:YES];
        [app run];
    }
    return 0;
}
