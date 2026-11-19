/// Shared byte contract for accepted originals and their encrypted derivatives.
public enum FullMessageBudget {
    public static let sourceBytes = 32_768
    public static let recordBytes = 2_097_152
    public static let residentBytes = 8 * 1024 * 1024
}
