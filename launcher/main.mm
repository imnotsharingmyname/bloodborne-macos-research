#import <Cocoa/Cocoa.h>

@interface Launcher : NSObject <NSApplicationDelegate>
@property(strong) NSWindow *window;
@property(strong) NSTextField *folderLabel;
@property(strong) NSTextField *status;
@property(strong) NSPopUpButton *resolution;
@property(strong) NSPopUpButton *fps;
@property(strong) NSPopUpButton *gpuMode;
@property(strong) NSButton *fsr;
@property(strong) NSButton *skip;
@property(strong) NSButton *perfDiagnostics;
@property(strong) NSButton *selectButton;
@property(strong) NSButton *launchButton;
@property(strong) NSTask *worker;
@property(strong) NSURL *gameURL;
@property(strong) NSURL *dataURL;
@property(strong) NSURL *logURL;
@property BOOL valid;
@property BOOL launching;
@property BOOL quitPending;
@end

@implementation Launcher
- (NSURL *)resources { return NSBundle.mainBundle.resourceURL; }
- (NSURL *)helper:(NSString *)name {
    return [[[NSBundle.mainBundle.bundleURL URLByAppendingPathComponent:@"Contents"]
             URLByAppendingPathComponent:@"Helpers"] URLByAppendingPathComponent:name];
}
- (BOOL)hasBackend {
    return [NSFileManager.defaultManager isExecutableFileAtPath:[self helper:@"bb-runtime"].path] &&
           [NSFileManager.defaultManager isExecutableFileAtPath:[self helper:@"python3.13"].path];
}
- (void)alert:(NSString *)title message:(NSString *)message {
    NSAlert *a = [NSAlert new];
    a.messageText = title;
    a.informativeText = message;
    [a addButtonWithTitle:@"OK"];
    [a beginSheetModalForWindow:self.window completionHandler:nil];
}
- (NSTextField *)label:(NSString *)title {
    NSTextField *f = [NSTextField wrappingLabelWithString:title];
    f.translatesAutoresizingMaskIntoConstraints = NO;
    return f;
}
- (NSButton *)button:(NSString *)title action:(SEL)selector {
    NSButton *b = [NSButton buttonWithTitle:title target:self action:selector];
    b.translatesAutoresizingMaskIntoConstraints = NO;
    return b;
}
- (void)updateControls {
    BOOL busy = self.worker != nil;
    self.selectButton.enabled = !busy && [self hasBackend];
    self.launchButton.enabled = !busy && self.valid && [self hasBackend];
    self.resolution.enabled = !busy;
    self.fps.enabled = !busy;
    self.gpuMode.enabled = !busy;
    self.fsr.enabled = !busy;
    self.skip.enabled = !busy;
    self.perfDiagnostics.enabled = !busy;
}
- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    (void)notification;
    NSMenu *menu = [NSMenu new];
    NSMenuItem *root = [NSMenuItem new];
    NSMenu *appMenu = [NSMenu new];
    [appMenu addItemWithTitle:@"Quit Bloodborne" action:@selector(terminate:) keyEquivalent:@"q"];
    root.submenu = appMenu;
    [menu addItem:root];
    NSApp.mainMenu = menu;
    NSURL *support = [NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory
                                                        inDomains:NSUserDomainMask].firstObject;
    self.dataURL = [support URLByAppendingPathComponent:@"BloodborneResearch" isDirectory:YES];
    [NSFileManager.defaultManager createDirectoryAtURL:self.dataURL
                           withIntermediateDirectories:YES attributes:nil error:nil];
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 660, 565)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"Bloodborne — Experimental macOS port";
    self.window.releasedWhenClosed = NO;
    NSStackView *stack = [NSStackView new];
    stack.orientation = NSUserInterfaceLayoutOrientationVertical;
    stack.alignment = NSLayoutAttributeLeading;
    stack.spacing = 14;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.window.contentView addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
        [stack.leadingAnchor constraintEqualToAnchor:self.window.contentView.leadingAnchor constant:24],
        [stack.trailingAnchor constraintEqualToAnchor:self.window.contentView.trailingAnchor constant:-24],
        [stack.topAnchor constraintEqualToAnchor:self.window.contentView.topAnchor constant:24],
        [stack.bottomAnchor constraintLessThanOrEqualToAnchor:self.window.contentView.bottomAnchor constant:-24]]];
    NSTextField *heading = [self label:@"Bloodborne"];
    heading.font = [NSFont boldSystemFontOfSize:25];
    [stack addArrangedSubview:heading];
    [stack addArrangedSubview:[self label:@"Select your decrypted CUSA03173 v1.09 folder. Game files are supplied separately."]];
    self.selectButton = [self button:@"Select Game Folder (CUSA03173)…" action:@selector(selectGame:)];
    [stack addArrangedSubview:self.selectButton];
    self.folderLabel = [self label:@"No game folder selected"];
    [stack addArrangedSubview:self.folderLabel];
    self.resolution = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    [self.resolution addItemsWithTitles:@[@"1280 × 720", @"1920 × 1080", @"2560 × 1440", @"3840 × 2160"]];
    self.fps = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    [self.fps addItemsWithTitles:@[@"30 FPS (recommended)", @"60 FPS patch (experimental)", @"90 FPS patch (experimental)"]];
    NSStackView *settings = [NSStackView stackViewWithViews:@[[self label:@"Output"], self.resolution,
                                                            [self label:@"Frame cap"], self.fps]];
    settings.spacing = 10;
    [stack addArrangedSubview:settings];
    self.gpuMode = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    [self.gpuMode addItemsWithTitles:@[@"Baseline (known working)", @"Queue 2 GPU frames (experimental)", @"Direct Vulkan recording (experimental)"]];
    NSStackView *gpuSettings = [NSStackView stackViewWithViews:@[
        [self label:@"GPU scheduling"], self.gpuMode]];
    gpuSettings.spacing = 10;
    [stack addArrangedSubview:gpuSettings];
    self.fsr = [NSButton checkboxWithTitle:@"FSR 3.1 Quality (experimental)" target:nil action:nil];
    self.skip = [NSButton checkboxWithTitle:@"Skip intro and warning screens" target:nil action:nil];
    [stack addArrangedSubview:self.fsr];
    [stack addArrangedSubview:self.skip];
    self.perfDiagnostics = [NSButton checkboxWithTitle:@"Collect frame/present/buffer diagnostics (experimental)" target:nil action:nil];
    [stack addArrangedSubview:self.perfDiagnostics];
    [stack addArrangedSubview:[self label:@"30 FPS is the starting target. Higher caps and upscaling do not guarantee performance or compatibility."]];
    NSStackView *actions = [NSStackView stackViewWithViews:@[
        self.launchButton = [self button:@"Launch Bloodborne" action:@selector(launch:)],
        [self button:@"Open Logs" action:@selector(openLogs:)],
        [self button:@"Open Saves" action:@selector(openSaves:)]]];
    actions.spacing = 12;
    [stack addArrangedSubview:actions];
    self.status = [self label:@"Choose a game folder to validate it."];
    [stack addArrangedSubview:self.status];
    if (![self hasBackend]) {
        self.status.stringValue = @"Launcher-only scaffold: no game runtime is bundled. Build the complete experimental app on a Mac.";
    }
    [self updateControls];
    [self.window center];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
    NSString *saved = [NSUserDefaults.standardUserDefaults stringForKey:@"GameFolder"];
    if (saved.length && [self hasBackend]) {
        self.gameURL = [NSURL fileURLWithPath:saved isDirectory:YES];
        self.folderLabel.stringValue = saved;
        [self validateGame];
    }
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    (void)sender; return YES;
}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    (void)sender;
    if (!self.worker) return NSTerminateNow;
    NSAlert *a = [NSAlert new];
    a.messageText = @"Stop the running task and quit?";
    a.informativeText = @"Exit the game normally first when possible so it can finish saving.";
    [a addButtonWithTitle:@"Stop and Quit"];
    [a addButtonWithTitle:@"Cancel"];
    if ([a runModal] != NSAlertFirstButtonReturn) return NSTerminateCancel;
    self.quitPending = YES;
    [self.worker terminate];
    return NSTerminateLater;
}
- (NSDictionary<NSString *, NSString *> *)workerEnvironment {
    NSMutableDictionary *env = [NSProcessInfo.processInfo.environment mutableCopy];
    for (NSString *key in env.allKeys) {
        if ([key hasPrefix:@"PYTHON"] || [key hasPrefix:@"DYLD_"]) [env removeObjectForKey:key];
    }
    env[@"PYTHONHOME"] = [[self resources] URLByAppendingPathComponent:@"python"].path;
    env[@"PYTHONNOUSERSITE"] = @"1";
    env[@"PYTHONDONTWRITEBYTECODE"] = @"1";
    env[@"PYTHONUNBUFFERED"] = @"1";
    env[@"PATH"] = @"/usr/bin:/bin:/usr/sbin:/sbin";
    return env;
}
- (NSTask *)taskWithArguments:(NSArray<NSString *> *)arguments {
    NSTask *task = [NSTask new];
    task.executableURL = [self helper:@"python3.13"];
    task.arguments = [@[[[[self resources] URLByAppendingPathComponent:@"backend"]
                         URLByAppendingPathComponent:@"launch.py"].path] arrayByAddingObjectsFromArray:arguments];
    task.environment = [self workerEnvironment];
    task.currentDirectoryURL = self.dataURL;
    return task;
}
- (void)selectGame:(id)sender {
    (void)sender;
    NSOpenPanel *p = [NSOpenPanel openPanel];
    p.canChooseDirectories = YES;
    p.canChooseFiles = NO;
    p.allowsMultipleSelection = NO;
    p.prompt = @"Select Game Folder";
    [p beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
        if (response == NSModalResponseOK) {
            self.gameURL = p.URL;
            self.folderLabel.stringValue = p.URL.path;
            [self validateGame];
        }
    }];
}
- (void)validateGame {
    self.valid = NO;
    self.status.stringValue = @"Validating files…";
    NSTask *task = [self taskWithArguments:@[@"--validate", @"--game", self.gameURL.path]];
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = [NSFileHandle fileHandleWithNullDevice];
    self.worker = task;
    [self updateControls];
    task.terminationHandler = ^(NSTask *completed) {
        NSData *data = [pipe.fileHandleForReading readDataToEndOfFile];
        id parsed = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
        NSDictionary *result = [parsed isKindOfClass:NSDictionary.class] ? parsed : nil;
        dispatch_async(dispatch_get_main_queue(), ^{
            self.worker = nil;
            self.valid = completed.terminationStatus == 0 && [result[@"ok"] boolValue];
            self.status.stringValue = result[@"message"] ?: @"Validation failed. Check that the dump is plaintext SELF and has its required modules.";
            if (self.valid) [NSUserDefaults.standardUserDefaults setObject:self.gameURL.path forKey:@"GameFolder"];
            [self updateControls];
            if (self.quitPending) [NSApp replyToApplicationShouldTerminate:YES];
        });
    };
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        self.worker = nil;
        self.status.stringValue = error.localizedDescription;
        [self updateControls];
    }
}
- (void)launch:(id)sender {
    (void)sender;
    if (!self.valid || self.worker) return;
    // Rosetta cannot be shipped inside this bundle. The OS manages its installation.
    NSTask *probe = [NSTask new];
    probe.executableURL = [NSURL fileURLWithPath:@"/usr/bin/arch"];
    probe.arguments = @[@"-x86_64", @"/usr/bin/true"];
    probe.standardError = [NSFileHandle fileHandleWithNullDevice];
    NSError *probeError = nil;
    BOOL started = [probe launchAndReturnError:&probeError];
    if (started) [probe waitUntilExit];
    if (!started || probe.terminationStatus != 0) {
        [self alert:@"Rosetta is required" message:@"This experimental runtime is x86-64. Install Rosetta using Apple's supported installation flow, then launch again. The application does not install or license Rosetta itself."];
        return;
    }
    NSArray *caps = @[@"30", @"60", @"90"];
    NSMutableArray *args = [@[@"--game", self.gameURL.path, @"--data", self.dataURL.path,
        @"--fps", caps[self.fps.indexOfSelectedItem], @"--resolution",
        [NSString stringWithFormat:@"%ld", (long)self.resolution.indexOfSelectedItem]] mutableCopy];
    if (self.fsr.state == NSControlStateValueOn) [args addObject:@"--fsr"];
    if (self.skip.state == NSControlStateValueOn) [args addObject:@"--skip-intro"];
    if (self.perfDiagnostics.state == NSControlStateValueOn) [args addObject:@"--perf-diagnostics"];
    NSArray *gpuModes = @[@"baseline", @"queue2", @"direct-record"];
    [args addObjectsFromArray:@[@"--gpu-mode", gpuModes[self.gpuMode.indexOfSelectedItem]]];
    NSURL *logs = [self.dataURL URLByAppendingPathComponent:@"logs" isDirectory:YES];
    [NSFileManager.defaultManager createDirectoryAtURL:logs withIntermediateDirectories:YES attributes:nil error:nil];
    self.logURL = [logs URLByAppendingPathComponent:[NSString stringWithFormat:@"launch-%@.log", NSUUID.UUID.UUIDString]];
    if (![NSFileManager.defaultManager createFileAtPath:self.logURL.path contents:[NSData data] attributes:nil]) {
        [self alert:@"Cannot write launch log" message:@"Check available disk space and Application Support permissions."];
        return;
    }
    NSFileHandle *log = [NSFileHandle fileHandleForWritingAtPath:self.logURL.path];
    NSTask *task = [self taskWithArguments:args];
    task.standardOutput = log;
    task.standardError = log;
    self.worker = task;
    self.status.stringValue = @"Preparing game files and starting the runtime…";
    [self updateControls];
    task.terminationHandler = ^(NSTask *completed) {
        [log closeFile];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.worker = nil;
            self.status.stringValue = completed.terminationStatus == 0 ? @"Game exited." :
                [NSString stringWithFormat:@"Runtime exited with status %d. Open Logs for details.", completed.terminationStatus];
            [self updateControls];
            if (self.quitPending) [NSApp replyToApplicationShouldTerminate:YES];
        });
    };
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) {
        self.worker = nil;
        [log closeFile];
        self.status.stringValue = error.localizedDescription;
        [self updateControls];
    }
}
- (void)openLogs:(id)sender {
    (void)sender;
    [NSWorkspace.sharedWorkspace openURL:[self.dataURL URLByAppendingPathComponent:@"logs"]];
}
- (void)openSaves:(id)sender {
    (void)sender;
    [NSWorkspace.sharedWorkspace openURL:[self.dataURL URLByAppendingPathComponent:@"user"]];
}
@end

int main(int argc, const char **argv) {
    (void)argc; (void)argv;
    @autoreleasepool {
        NSApplication *app = NSApplication.sharedApplication;
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        __attribute__((objc_precise_lifetime)) Launcher *delegate = [Launcher new];
        app.delegate = delegate;
        [app run];
    }
    return 0;
}
