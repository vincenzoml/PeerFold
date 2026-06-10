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

- (void)cancelPendingPrompt {
    [NSObject cancelPreviousPerformRequestsWithTarget:self
                                             selector:@selector(promptForPDFIfNeeded)
                                               object:nil];
}

- (void)openPDFPath:(NSString *)path {
    if (!PathLooksLikePDF(path)) {
        return;
    }
    self.opened = YES;
    [self cancelPendingPrompt];
    LaunchPeerFold(path);
}

- (BOOL)application:(NSApplication *)application openFile:(NSString *)filename {
    [self openPDFPath:filename];
    return self.opened;
}

- (void)application:(NSApplication *)application openFiles:(NSArray<NSString *> *)filenames {
    for (NSString *filename in filenames) {
        [self openPDFPath:filename];
        if (self.opened) {
            return;
        }
    }
}

- (void)application:(NSApplication *)application openURLs:(NSArray<NSURL *> *)urls {
    for (NSURL *url in urls) {
        if (!url.isFileURL) {
            continue;
        }
        [self openPDFPath:url.path];
        if (self.opened) {
            return;
        }
    }
}

- (void)handleOpenDocumentsEvent:(NSAppleEventDescriptor *)event
                  withReplyEvent:(NSAppleEventDescriptor *)replyEvent {
    NSAppleEventDescriptor *directObject = [event paramDescriptorForKeyword:keyDirectObject];
    if (!directObject) {
        return;
    }
    NSInteger count = directObject.numberOfItems;
    for (NSInteger i = 1; i <= count; i++) {
        NSAppleEventDescriptor *item = [directObject descriptorAtIndex:i];
        NSURL *url = item.fileURLValue;
        if (url.isFileURL) {
            [self openPDFPath:url.path];
            if (self.opened) {
                return;
            }
        }
    }
}

- (void)applicationWillFinishLaunching:(NSNotification *)notification {
    [[NSAppleEventManager sharedAppleEventManager]
        setEventHandler:self
        andSelector:@selector(handleOpenDocumentsEvent:withReplyEvent:)
        forEventClass:kCoreEventClass
        andEventID:kAEOpenDocuments];
}

- (void)promptForPDF {
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.allowedContentTypes = @[UTTypePDF];
    panel.canChooseFiles = YES;
    panel.canChooseDirectories = NO;
    panel.allowsMultipleSelection = NO;
    panel.prompt = @"Open";
    panel.message = @"Choose a PDF to review";
    [panel beginWithCompletionHandler:^(NSModalResponse result) {
        if (result == NSModalResponseOK) {
            LaunchPeerFold(panel.URL.path);
        }
        [NSApp terminate:nil];
    }];
}

- (void)promptForPDFIfNeeded {
    if (!self.opened) {
        [self promptForPDF];
    }
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    NSArray<NSString *> *args = [[NSProcessInfo processInfo] arguments];
    for (NSUInteger i = 1; i < args.count; i++) {
        [self openPDFPath:[args objectAtIndex:i]];
        if (self.opened) {
            return;
        }
    }
    [self performSelector:@selector(promptForPDFIfNeeded) withObject:nil afterDelay:1.0];
}

@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        if (argc > 1) {
            NSString *path = [NSString stringWithUTF8String:argv[1]];
            if (PathLooksLikePDF(path)) {
                LaunchPeerFold(path);
            }
        }

        NSApplication *app = [NSApplication sharedApplication];
        AppDelegate *delegate = [[AppDelegate alloc] init];
        app.delegate = delegate;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        [app run];
    }
    return 0;
}
